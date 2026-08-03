"""Regression tests for repository working-tree credential scanning."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scan_repository_secrets as scanner  # noqa: E402


class RepositorySecretScanTests(unittest.TestCase):
    def test_sensitive_key_variants_are_detected(self):
        text = "\n".join([
            "openai_api_key = live-value-1234",  # secret-scan: allow
            "session_token: abcdefghijklmnop",  # secret-scan: allow
            "accessToken=abcdefghijklmnop",  # secret-scan: allow
            "clientSecretValue: abcdefghijklmnop",  # secret-scan: allow
        ])
        self.assertEqual(len(scanner.scan_text(text, "fixture.env")), 4)

    def test_redacted_and_environment_references_are_allowed(self):
        text = "api_key=<redacted>\naccess_token=${ACCESS_TOKEN}\n"  # secret-scan: allow
        self.assertEqual(scanner.scan_text(text, "fixture.env"), [])


if __name__ == "__main__":
    unittest.main()
