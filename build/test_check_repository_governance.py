#!/usr/bin/env python3

import json
from pathlib import Path
import sys
import unittest


BUILD_DIR = Path(__file__).resolve().parent
if str(BUILD_DIR) not in sys.path:
    sys.path.insert(0, str(BUILD_DIR))

import check_repository_governance as governance


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self.payload

    def close(self):
        pass


def good_ruleset(**updates):
    ruleset = {
        "id": 7,
        "name": "Protect main evidence history",
        "target": "branch",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {
            "ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}
        },
        "rules": [
            {"type": "pull_request", "parameters": {"required_approving_review_count": 1}},
            {"type": "required_status_checks", "parameters": {
                "required_status_checks": [{"context": "build"}]
            }},
            {"type": "non_fast_forward"},
            {"type": "deletion"},
        ],
    }
    ruleset.update(updates)
    return ruleset


def fake_getter(branch_payload=None, rulesets=None):
    branch_payload = branch_payload or {"name": "main", "protected": True}
    rulesets = [good_ruleset()] if rulesets is None else rulesets

    def get(request, timeout):
        url = request.full_url
        if "/branches/main" in url:
            return FakeResponse(branch_payload)
        if url.endswith("/rulesets?includes_parents=true"):
            return FakeResponse(rulesets)
        if "/rulesets/" in url:
            ruleset_id = int(url.rsplit("/", 1)[-1])
            return FakeResponse(next(r for r in rulesets if r["id"] == ruleset_id))
        raise AssertionError(url)

    return get


class RepositoryGovernanceTests(unittest.TestCase):
    def inspect(self, **kwargs):
        return governance.inspect_governance(
            "Goodrich-Dev/task-library", getter=fake_getter(**kwargs)
        )

    def test_accepts_active_no_bypass_default_branch_ruleset(self):
        report = self.inspect()
        self.assertEqual(report["errors"], [])
        self.assertIn("build", report["requiredStatusContexts"])

    def test_fails_when_branch_is_not_protected(self):
        report = self.inspect(branch_payload={"name": "main", "protected": False})
        self.assertIn("main is not protected", report["errors"])

    def test_fails_without_applicable_ruleset(self):
        report = self.inspect(rulesets=[])
        self.assertIn(
            "no active matching branch ruleset without bypass actors", report["errors"]
        )

    def test_bypass_actors_make_ruleset_nonqualifying(self):
        ruleset = good_ruleset(bypass_actors=[{"actor_type": "OrganizationAdmin"}])
        report = self.inspect(rulesets=[ruleset])
        self.assertTrue(report["errors"])
        self.assertEqual(report["noBypassRulesets"], [])

    def test_excluded_or_wrong_branch_ruleset_does_not_apply(self):
        ruleset = good_ruleset(conditions={
            "ref_name": {
                "include": ["refs/heads/release/*"],
                "exclude": ["refs/heads/main"],
            }
        })
        report = self.inspect(rulesets=[ruleset])
        self.assertEqual(report["matchingRulesets"], [])

    def test_requires_review_and_named_build_check(self):
        ruleset = good_ruleset()
        ruleset["rules"][0]["parameters"]["required_approving_review_count"] = 0
        ruleset["rules"][1]["parameters"]["required_status_checks"] = [
            {"context": "lint"}
        ]
        report = self.inspect(rulesets=[ruleset])
        self.assertIn(
            "pull-request rule does not require an approving review", report["errors"]
        )
        self.assertIn('required status check "build" is not enforced', report["errors"])

    def test_fetches_ruleset_details_when_list_response_is_summary(self):
        summary = {"id": 7, "name": "summary", "target": "branch", "enforcement": "active"}
        details = good_ruleset()

        def getter(request, timeout):
            url = request.full_url
            if "/branches/main" in url:
                return FakeResponse({"name": "main", "protected": True})
            if url.endswith("/rulesets?includes_parents=true"):
                return FakeResponse([summary])
            if url.endswith("/rulesets/7"):
                return FakeResponse(details)
            raise AssertionError(url)

        report = governance.inspect_governance(
            "Goodrich-Dev/task-library", getter=getter
        )
        self.assertEqual(report["errors"], [])


if __name__ == "__main__":
    unittest.main()

