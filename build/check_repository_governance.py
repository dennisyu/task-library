#!/usr/bin/env python3
"""Fail a trusted deployment unless main has a verifiable no-bypass ruleset.

Append-only checks inside CI are useful alarms, but they run after a direct push
has already changed the branch. This gate verifies the external control that
makes the history policy preventive: an active GitHub ruleset requiring pull
requests, review, the build check, and protection from force-push/deletion.
"""

import argparse
import fnmatch
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


API_VERSION = "2022-11-28"


class GovernanceError(RuntimeError):
    pass


def api_get(url, getter=urlopen):
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "TaskLibraryGovernanceCheck/1.0",
        },
    )
    try:
        response = getter(request, timeout=15)
        try:
            return json.loads(response.read().decode("utf-8"))
        finally:
            response.close()
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        raise GovernanceError(f"GitHub governance API failed closed: {exc}") from exc


def ref_matches(pattern, branch, default_branch):
    if pattern == "~DEFAULT_BRANCH":
        return branch == default_branch
    if pattern == "~ALL":
        return True
    return fnmatch.fnmatchcase(f"refs/heads/{branch}", pattern)


def ruleset_applies(ruleset, branch, default_branch):
    if ruleset.get("target") != "branch" or ruleset.get("enforcement") != "active":
        return False
    ref_name = (ruleset.get("conditions") or {}).get("ref_name") or {}
    includes = ref_name.get("include") or []
    excludes = ref_name.get("exclude") or []
    return (
        any(ref_matches(pattern, branch, default_branch) for pattern in includes)
        and not any(ref_matches(pattern, branch, default_branch) for pattern in excludes)
    )


def inspect_governance(repository, branch="main", required_check="build",
                       api_base="https://api.github.com", getter=urlopen):
    repo_path = "/".join(quote(part, safe="") for part in repository.split("/"))
    branch_url = f"{api_base.rstrip('/')}/repos/{repo_path}/branches/{quote(branch, safe='')}"
    branch_data = api_get(branch_url, getter)
    default_branch = branch_data.get("name") or branch
    errors = []
    if branch_data.get("protected") is not True:
        errors.append(f"{branch} is not protected")

    list_url = f"{api_base.rstrip('/')}/repos/{repo_path}/rulesets?includes_parents=true"
    summaries = api_get(list_url, getter)
    if not isinstance(summaries, list):
        raise GovernanceError("GitHub rulesets response was not an array")

    applicable = []
    for summary in summaries:
        details = summary
        if not details.get("rules") or not details.get("conditions"):
            ruleset_id = details.get("id")
            if ruleset_id is None:
                continue
            details = api_get(
                f"{api_base.rstrip('/')}/repos/{repo_path}/rulesets/{ruleset_id}",
                getter,
            )
        if ruleset_applies(details, branch, default_branch):
            applicable.append(details)

    no_bypass = [r for r in applicable if not (r.get("bypass_actors") or [])]
    if not no_bypass:
        errors.append("no active matching branch ruleset without bypass actors")

    rule_types = set()
    status_contexts = set()
    approval_count = 0
    for ruleset in no_bypass:
        for rule in ruleset.get("rules") or []:
            rule_type = rule.get("type")
            if rule_type:
                rule_types.add(rule_type)
            params = rule.get("parameters") or {}
            if rule_type == "required_status_checks":
                status_contexts.update(
                    check.get("context")
                    for check in params.get("required_status_checks") or []
                    if check.get("context")
                )
            if rule_type == "pull_request":
                approval_count = max(
                    approval_count,
                    int(params.get("required_approving_review_count") or 0),
                )

    for required_type in ("pull_request", "required_status_checks",
                          "non_fast_forward", "deletion"):
        if required_type not in rule_types:
            errors.append(f"missing active {required_type} rule")
    if approval_count < 1:
        errors.append("pull-request rule does not require an approving review")
    if required_check not in status_contexts:
        errors.append(f'required status check "{required_check}" is not enforced')

    return {
        "repository": repository,
        "branch": branch,
        "protected": branch_data.get("protected") is True,
        "matchingRulesets": [r.get("name") or str(r.get("id")) for r in applicable],
        "noBypassRulesets": [r.get("name") or str(r.get("id")) for r in no_bypass],
        "ruleTypes": sorted(rule_types),
        "requiredStatusContexts": sorted(status_contexts),
        "requiredApprovingReviewCount": approval_count,
        "errors": errors,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, help="GitHub owner/repository")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--required-check", default="build")
    parser.add_argument("--api-base", default="https://api.github.com")
    args = parser.parse_args(argv)
    try:
        report = inspect_governance(
            args.repository, args.branch, args.required_check, args.api_base
        )
    except GovernanceError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True))
    if report["errors"]:
        for error in report["errors"]:
            print(f"governance: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

