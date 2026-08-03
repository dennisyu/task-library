"""Tests for append-only evidence records and version artifacts."""

import json
import unittest

import check_evidence_append_only as append_only


def schema(version: str) -> str:
    return json.dumps({
        "$id": f"https://example.test/evidence/schemas/{version}.json",
        "properties": {"schemaVersion": {"const": version}},
    })


def policy(version: str, schema_version: str = "1.0") -> str:
    return json.dumps({"policyVersion": version, "schemaVersion": schema_version})


class AppendOnlyEvidenceTests(unittest.TestCase):
    def test_record_and_higher_version_additions_are_potentially_allowed(self):
        diff = (
            "A\tevidence/records/task/trial.json\n"
            "A\tevidence/policies/2.0.json\n"
            "A\tevidence/schemas/2.0.json\n"
        )
        self.assertEqual(append_only.violations(diff), [])
        problems = append_only.version_addition_violations(
            diff,
            {"evidence/policies/1.0.json", "evidence/schemas/1.0.json"},
            {
                "evidence/policies/1.0.json", "evidence/policies/2.0.json",
                "evidence/schemas/1.0.json", "evidence/schemas/2.0.json",
            },
            {
                "evidence/policies/2.0.json": policy("2.0", "2.0"),
                "evidence/schemas/2.0.json": schema("2.0"),
            },
        )
        self.assertEqual(problems, [])

    def test_edits_deletes_renames_and_copies_of_protected_files_are_rejected(self):
        diff = (
            "M\tevidence/records/task/old.json\n"
            "D\tevidence/policies/1.0.json\n"
            "R100\tevidence/schemas/1.0.json\tevidence/schemas/2.0.json\n"
            "C100\tevidence/records/task/a.json\tevidence/records/task/b.json\n"
            "M\tevidence/README.md\n"
        )
        self.assertEqual(len(append_only.violations(diff)), 4)

    def test_status_filter_only_protects_json_artifacts_in_declared_scopes(self):
        diff = (
            "M\tevidence/records/README.md\n"
            "M\tevidence/policies/notes.txt\n"
            "M\tevidence/archive/1.0.json\n"
            "M\tevidence/schemas/1.0.json\n"
        )
        self.assertEqual(
            append_only.violations(diff), ["M\tevidence/schemas/1.0.json"]
        )

    def test_filename_internal_version_and_monotonicity_are_enforced(self):
        diff = (
            "A\tevidence/policies/0.9.json\n"
            "A\tevidence/schemas/v2.json\n"
            "A\tevidence/policies/2.0.json\n"
        )
        problems = append_only.version_addition_violations(
            diff,
            {"evidence/policies/1.0.json", "evidence/schemas/1.0.json"},
            {
                "evidence/policies/0.9.json", "evidence/policies/2.0.json",
                "evidence/schemas/1.0.json", "evidence/schemas/v2.json",
            },
            {
                "evidence/policies/0.9.json": policy("0.9"),
                "evidence/schemas/v2.json": schema("2.0"),
                "evidence/policies/2.0.json": policy("2.1"),
            },
        )
        self.assertTrue(any("must be higher" in problem for problem in problems))
        self.assertTrue(any("filename must be a semantic version" in problem
                            for problem in problems))
        self.assertTrue(any("policyVersion" in problem and "must match" in problem
                            for problem in problems))

    def test_policy_must_reference_schema_present_in_head(self):
        diff = "A\tevidence/policies/2.0.json\n"
        problems = append_only.version_addition_violations(
            diff,
            {"evidence/policies/1.0.json", "evidence/schemas/1.0.json"},
            {"evidence/policies/2.0.json", "evidence/schemas/1.0.json"},
            {"evidence/policies/2.0.json": policy("2.0", "2.0")},
        )
        self.assertTrue(any("absent from the head tree" in problem for problem in problems))

    def test_event_range_and_zero_sha_support_post_receive_push_alarm(self):
        base = "a" * 40
        self.assertEqual(
            append_only.comparison_range(base, "HEAD", "pull_request")[1],
            f"{base}...HEAD",
        )
        self.assertEqual(
            append_only.comparison_range(base, "HEAD", "push")[1],
            f"{base}..HEAD",
        )
        empty_base, revision_range, is_empty = append_only.comparison_range(
            "0" * 40, "HEAD", "push"
        )
        self.assertTrue(is_empty)
        self.assertEqual(empty_base, append_only.EMPTY_TREE_SHA)
        self.assertEqual(revision_range, f"{append_only.EMPTY_TREE_SHA}..HEAD")


if __name__ == "__main__":
    unittest.main()
