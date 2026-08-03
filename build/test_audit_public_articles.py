#!/usr/bin/env python3

from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest


BUILD_DIR = Path(__file__).resolve().parent
if str(BUILD_DIR) not in sys.path:
    sys.path.insert(0, str(BUILD_DIR))

import audit_public_articles as audit


def fetch_result(url, html, status=200, redirects=None, content_type="text/html; charset=utf-8"):
    return {
        "status": status,
        "finalUrl": url,
        "redirectChain": redirects or [],
        "contentType": content_type,
        "body": html.encode("utf-8"),
        "bodyTruncated": False,
        "durationMs": 1.2,
        "fetchError": None,
    }


class PublicArticleAuditTests(unittest.TestCase):
    def test_collect_targets_deduplicates_and_retains_task_slugs(self):
        data = {
            "categories": [
                {
                    "tasks": [
                        {"slug": "one", "article": "https://BLITZMETRICS.com/example/"},
                        {"slug": "two", "article": "https://blitzmetrics.com/example#section"},
                        {"slug": "three", "article": "/example"},
                        {"slug": "gap", "article": None},
                    ]
                }
            ]
        }
        targets, inventory = audit.collect_targets(data)
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["sourceUrl"], "https://blitzmetrics.com/example/")
        self.assertEqual(targets[0]["taskSlugs"], ["one", "three", "two"])
        self.assertEqual(inventory["tasksSeen"], 4)
        self.assertEqual(inventory["tasksWithArticle"], 3)
        self.assertEqual(inventory["duplicateArticleReferences"], 2)

    def test_normalization_preserves_request_trailing_slash(self):
        with_slash, error = audit.normalize_article_url(
            "https://blitzmetrics.com/example/"
        )
        self.assertIsNone(error)
        self.assertEqual(with_slash, "https://blitzmetrics.com/example/")
        self.assertEqual(
            audit.canonical_identity(with_slash),
            audit.canonical_identity("https://www.blitzmetrics.com/example"),
        )

    def test_clean_article_passes_transparent_content_threshold(self):
        body = " ".join(f"word{index}" for index in range(120))
        html = (
            "<html><head><title>Useful task</title>"
            '<link rel="canonical" href="https://blitzmetrics.com/useful/">'
            f"</head><body><main><h1>Do it</h1><p>{body}</p></main></body></html>"
        )

        def fake_fetch(url, **_kwargs):
            return fetch_result(url, html)

        data = {"tasks": [{"slug": "useful", "article": "/useful"}]}
        report = audit.audit_data(data, fetcher=fake_fetch)
        result = report["results"][0]
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["contentSignals"]["contentSelector"], "main/article")
        self.assertGreaterEqual(result["contentSignals"]["contentWords"], 120)
        self.assertTrue(result["contentSignals"]["canonical"]["matchesFinal"])
        self.assertEqual(result["findings"], [])
        self.assertEqual(audit.report_exit_code(report, strict=True), 0)

    def test_flags_cross_site_login_and_effectively_empty_body(self):
        source = "https://blitzmetrics.com/private-task"
        final = "https://accounts.example.net/login"
        html = "<html><head><title>Sign In</title></head><body><main><h1>Sign in</h1><form><input type='password'></form></main></body></html>"

        def fake_fetch(_url, **_kwargs):
            result = fetch_result(
                final,
                html,
                redirects=[{"from": source, "to": final, "status": 302}],
            )
            return result

        report = audit.audit_data(
            {"tasks": [{"slug": "private-task", "article": source}]},
            fetcher=fake_fetch,
        )
        result = report["results"][0]
        codes = {finding["code"] for finding in result["findings"]}
        self.assertIn("unexpected-cross-site-redirect", codes)
        self.assertIn("login-page", codes)
        self.assertIn("effectively-empty-body", codes)
        self.assertEqual(result["redirect"]["unexpectedHosts"], ["accounts.example.net"])
        self.assertEqual(audit.report_exit_code(report, strict=False), 0)
        self.assertEqual(audit.report_exit_code(report, strict=True), 1)

    def test_flags_http_and_soft_error_pages(self):
        html = "<html><head><title>404 - Page not found</title></head><body><main><h1>Page not found</h1></main></body></html>"

        def fake_fetch(url, **_kwargs):
            return fetch_result(url, html, status=404)

        report = audit.audit_data(
            {"tasks": [{"slug": "missing", "article": "/missing"}]},
            fetcher=fake_fetch,
        )
        codes = {finding["code"] for finding in report["results"][0]["findings"]}
        self.assertIn("http-error-status", codes)
        self.assertIn("error-page", codes)
        self.assertIn("effectively-empty-body", codes)

    def test_invalid_url_is_reported_without_network(self):
        calls = []

        def fake_fetch(url, **_kwargs):
            calls.append(url)
            raise AssertionError("network must not be called")

        report = audit.audit_data(
            {"tasks": [{"slug": "bad", "article": "javascript:alert(1)"}]},
            fetcher=fake_fetch,
        )
        self.assertEqual(calls, [])
        self.assertEqual(
            report["results"][0]["findings"][0]["code"], "invalid-article-url"
        )

    def test_source_hosts_private_ips_and_sensitive_queries_are_blocked_pre_fetch(self):
        calls = []

        def fake_fetch(url, **_kwargs):
            calls.append(url)
            raise AssertionError("blocked sources must never reach the fetcher")

        data = {
            "tasks": [
                {"slug": "foreign", "article": "https://evil.example/task"},
                {"slug": "loopback", "article": "http://127.0.0.1/admin"},
                {
                    "slug": "signed",
                    "article": "https://blitzmetrics.com/task?X-Amz-Signature=super-secret",
                },
            ]
        }
        config = audit.AuditConfig(allowed_source_hosts=("127.0.0.1",))
        report = audit.audit_data(data, config=config, fetcher=fake_fetch)
        self.assertEqual(calls, [])
        by_slug = {result["taskSlugs"][0]: result for result in report["results"]}
        self.assertEqual(
            by_slug["foreign"]["findings"][0]["code"], "blocked-source-host"
        )
        self.assertEqual(
            by_slug["loopback"]["findings"][0]["code"], "blocked-source-host"
        )
        self.assertEqual(
            by_slug["signed"]["findings"][0]["code"], "invalid-article-url"
        )
        self.assertNotIn("super-secret", json.dumps(report))
        self.assertIn("redacted", json.dumps(report))

    def test_dns_private_source_is_rejected_before_opener(self):
        opener_calls = []

        def private_resolver(_host, _port, **_kwargs):
            return [(None, None, None, None, ("10.0.0.8", 443))]

        result = audit.fetch_url(
            "https://allowed.example/task",
            timeout=2,
            max_bytes=100,
            user_agent="Audit Test/1.0",
            allowed_source_hosts={"allowed.example"},
            resolver=private_resolver,
            opener_factory=lambda _handler: opener_calls.append(True),
        )
        self.assertEqual(opener_calls, [])
        self.assertEqual(result["fetchError"]["type"], "BlockedSourceDestination")
        self.assertIn("non-public address", result["fetchError"]["message"])

    def test_redirect_handler_vetoes_unexpected_private_and_signed_destinations(self):
        def public_resolver(_host, _port, **_kwargs):
            return [(None, None, None, None, ("93.184.216.34", 443))]

        cases = [
            (
                {"blitzmetrics.com"},
                "https://evil.example/private",
                "not explicitly allowed",
            ),
            (
                {"blitzmetrics.com", "127.0.0.1"},
                "http://127.0.0.1/admin",
                "not globally routable",
            ),
            (
                {"blitzmetrics.com"},
                "https://blitzmetrics.com/login?token=secret-value",
                "sensitive query",
            ),
        ]
        for allowed, destination, expected in cases:
            with self.subTest(destination=destination):
                handler = audit.RecordingRedirectHandler(allowed, public_resolver)
                request = audit.Request("https://blitzmetrics.com/task")
                with self.assertRaisesRegex(audit.BlockedDestinationError, expected):
                    handler.redirect_request(request, None, 302, "Found", {}, destination)
                self.assertFalse(handler.history[0]["followed"])
                self.assertIn("blockedReason", handler.history[0])
                if "token=" in destination:
                    self.assertNotIn("secret-value", json.dumps(handler.history))

    def test_canonical_findings_cover_missing_cross_host_and_non_final(self):
        body = " ".join("content" for _ in range(100))
        pages = {
            "/missing": f"<html><head><title>Missing</title></head><body><main>{body}</main></body></html>",
            "/cross": f'<html><head><title>Cross</title><link rel="canonical" href="https://other.example/cross"></head><body><main>{body}</main></body></html>',
            "/wrong": f'<html><head><title>Wrong</title><link rel="canonical" href="/different"></head><body><main>{body}</main></body></html>',
        }

        def fake_fetch(url, **_kwargs):
            return fetch_result(url, pages[urlsplit(url).path])

        from urllib.parse import urlsplit

        report = audit.audit_data(
            {
                "tasks": [
                    {"slug": "missing", "article": "/missing"},
                    {"slug": "cross", "article": "/cross"},
                    {"slug": "wrong", "article": "/wrong"},
                ]
            },
            fetcher=fake_fetch,
        )
        codes = {
            result["taskSlugs"][0]: {item["code"] for item in result["findings"]}
            for result in report["results"]
        }
        self.assertEqual(codes["missing"], {"missing-canonical"})
        self.assertEqual(codes["cross"], {"cross-host-canonical"})
        self.assertEqual(codes["wrong"], {"non-final-canonical"})
        self.assertEqual(audit.report_exit_code(report, strict=True), 1)

    def test_fetch_layer_uses_get_user_agent_timeout_cap_and_no_cookies(self):
        captured = {}

        class FakeResponse:
            status = 200
            headers = {"Content-Type": "text/html"}

            def read(self, limit):
                captured["readLimit"] = limit
                return b"x" * limit

            def getcode(self):
                return self.status

            def geturl(self):
                return "https://blitzmetrics.com/example"

            def close(self):
                captured["closed"] = True

        class FakeOpener:
            def open(self, request, timeout):
                captured["method"] = request.get_method()
                captured["headers"] = dict(request.header_items())
                captured["timeout"] = timeout
                return FakeResponse()

        result = audit.fetch_url(
            "https://blitzmetrics.com/example",
            timeout=3.5,
            max_bytes=10,
            user_agent="Audit Test/1.0",
            allowed_source_hosts={"blitzmetrics.com"},
            resolver=lambda _host, _port, **_kwargs: [
                (None, None, None, None, ("93.184.216.34", 443))
            ],
            opener_factory=lambda _handler: FakeOpener(),
        )
        headers = {key.lower(): value for key, value in captured["headers"].items()}
        self.assertEqual(captured["method"], "GET")
        self.assertEqual(captured["timeout"], 3.5)
        self.assertEqual(captured["readLimit"], 11)
        self.assertEqual(headers["user-agent"], "Audit Test/1.0")
        self.assertEqual(headers["x-task-library-audit"], audit.AUDIT_HEADER_VALUE)
        self.assertNotIn("cookie", headers)
        self.assertTrue(captured["closed"])
        self.assertTrue(result["bodyTruncated"])
        self.assertEqual(len(result["body"]), 10)

    def test_cli_writes_valid_json_and_strict_policy_is_report_driven(self):
        data = {"tasks": []}
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "data.json"
            output_path = Path(directory) / "audit.json"
            input_path.write_text(json.dumps(data), encoding="utf-8")
            with redirect_stderr(io.StringIO()):
                code = audit.main(
                    ["--input", str(input_path), "--out", str(output_path), "--strict"]
                )
            report = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual(report["summary"]["auditedUrls"], 0)
        self.assertIs(report["requestPolicy"]["cookies"], False)


if __name__ == "__main__":
    unittest.main()
