#!/usr/bin/env python3
"""Structural guardrails for the Task Library's GitHub intake forms."""

import json
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
ISSUE_DIR = ROOT / ".github" / "ISSUE_TEMPLATE"
FORM_REQUIREMENTS = {
    "task-contract.yml": {
        "change_kind",
        "task_slug",
        "category",
        "task_outcome",
        "owner_reviewer",
        "canonical_url",
        "skill_source",
        "inputs_access",
        "acceptance",
        "failure_rollback",
        "examples",
        "truth_checks",
    },
    "evidence-trial.yml": {
        "task_slug",
        "target_level",
        "owner_reviewer",
        "exact_source",
        "hypothesis",
        "protocol_cases_arms",
        "acceptance",
        "stack_access",
        "artifact_plan",
        "operational_capture",
        "stops_rollback",
        "freshness",
        "evidence_checks",
    },
}
ALLOWED_TYPES = {"markdown", "input", "textarea", "dropdown", "checkboxes"}


def load_yaml(path):
    """Use Ruby's standard-library YAML parser; emit JSON for Python checks."""
    ruby = shutil.which("ruby")
    if not ruby:
        raise RuntimeError("ruby is required to syntax-check GitHub issue YAML")
    script = (
        "require 'yaml'; require 'json'; "
        "data = YAML.safe_load(File.read(ARGV.fetch(0)), "
        "permitted_classes: [], aliases: false); puts JSON.generate(data)"
    )
    result = subprocess.run(
        [ruby, "-e", script, str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


class IssueFormTests(unittest.TestCase):
    def test_config_disables_unstructured_intake(self):
        config = load_yaml(ISSUE_DIR / "config.yml")
        self.assertIs(config.get("blank_issues_enabled"), False)

    def test_forms_parse_and_keep_required_guardrails(self):
        for filename, required_ids in FORM_REQUIREMENTS.items():
            with self.subTest(filename=filename):
                form = load_yaml(ISSUE_DIR / filename)
                self.assertTrue(form.get("name"))
                self.assertTrue(form.get("description"))
                self.assertTrue(form.get("title"))
                self.assertIsInstance(form.get("body"), list)

                ids = []
                for item in form["body"]:
                    item_type = item.get("type")
                    self.assertIn(item_type, ALLOWED_TYPES)
                    self.assertIsInstance(item.get("attributes"), dict)
                    if item_type == "markdown":
                        self.assertTrue(item["attributes"].get("value"))
                        continue
                    self.assertTrue(item.get("id"))
                    self.assertTrue(item["attributes"].get("label"))
                    ids.append(item["id"])

                    if item_type == "checkboxes":
                        options = item["attributes"].get("options", [])
                        self.assertGreaterEqual(len(options), 1)
                        self.assertTrue(all(option.get("required") is True for option in options))
                    else:
                        self.assertIs(item.get("validations", {}).get("required"), True)
                    if item_type == "dropdown":
                        self.assertGreaterEqual(len(item["attributes"].get("options", [])), 2)

                self.assertEqual(len(ids), len(set(ids)), "interactive IDs must be unique")
                self.assertTrue(required_ids.issubset(ids))


if __name__ == "__main__":
    unittest.main()
