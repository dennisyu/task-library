#!/usr/bin/env python3

from pathlib import Path
import sys
import unittest


BUILD_DIR = Path(__file__).resolve().parent
if str(BUILD_DIR) not in sys.path:
    sys.path.insert(0, str(BUILD_DIR))

import audit_public_articles as public_audit
import audit_task_pages as task_pages


def good_html(url):
    words = " ".join(f"word{index}" for index in range(100))
    return (
        "<html><head><title>Exact task</title>"
        f'<link rel="canonical" href="{url}"></head>'
        f"<body><main><h1>Exact task</h1><p>{words}</p></main></body></html>"
    )


def fake_fetch(url, **_kwargs):
    return {
        "status": 200,
        "finalUrl": url,
        "redirectChain": [],
        "contentType": "text/html; charset=utf-8",
        "body": good_html(url).encode("utf-8"),
        "bodyTruncated": False,
        "durationMs": 1,
        "fetchError": None,
    }


class TaskPageAuditTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            "categories": [{"tasks": [
                {"slug": "one"}, {"slug": "two"}, {"slug": "three"}
            ]}]
        }

    def test_separates_task_page_coverage_and_deduplicates_alias_health_check(self):
        crosswalk = {
            "reviewedAt": "2026-08-02",
            "tasks": {
                "one": {
                    "url": "https://blitzmetrics.com/task-one/",
                    "matchMethod": "manual-content-review",
                },
                "two": {
                    "url": "https://blitzmetrics.com/task-one/",
                    "matchMethod": "legacy-alias",
                    "canonicalTask": "one",
                },
            },
        }
        report = task_pages.build_report(self.data, crosswalk, fetcher=fake_fetch)
        self.assertEqual(report["mapping"]["mappedTaskRecords"], 2)
        self.assertEqual(report["mapping"]["unmappedTaskRecords"], 1)
        self.assertEqual(report["mapping"]["uniqueTaskPages"], 1)
        self.assertEqual(report["mapping"]["legacyAliasRecords"], 1)
        self.assertEqual(report["publicHealth"]["summary"]["auditedUrls"], 1)
        self.assertEqual(
            report["publicHealth"]["results"][0]["taskSlugs"], ["one", "two"]
        )
        self.assertEqual(task_pages.report_exit_code(report, strict=True), 0)

    def test_unknown_slug_and_bad_alias_fail_strict_validation(self):
        crosswalk = {
            "tasks": {
                "missing": {
                    "url": "https://blitzmetrics.com/task/",
                    "matchMethod": "manual-content-review",
                    "canonicalTask": "also-missing",
                }
            }
        }
        report = task_pages.build_report(self.data, crosswalk, fetcher=fake_fetch)
        joined = " ".join(report["mapping"]["errors"])
        self.assertIn("unknown catalog task", joined)
        self.assertIn("canonicalTask is not a catalog task", joined)
        self.assertEqual(task_pages.report_exit_code(report, strict=True), 1)

    def test_rejects_non_public_or_credential_bearing_mapping(self):
        for url in (
            "http://127.0.0.1/private",
            "https://evil.example/task/",
            "https://blitzmetrics.com/task/?token=secret-value",
        ):
            with self.subTest(url=url):
                crosswalk = {
                    "tasks": {
                        "one": {"url": url, "matchMethod": "manual-content-review"}
                    }
                }
                errors, _tasks, mappings = task_pages.validate_crosswalk(
                    self.data, crosswalk
                )
                self.assertTrue(errors)
                self.assertEqual(mappings, {})

    def test_accepts_explicit_local_service_spotlight_task_page(self):
        crosswalk = {
            "tasks": {
                "one": {
                    "url": "https://localservicespotlight.com/how-to-do-one/",
                    "matchMethod": "manual-content-review",
                }
            }
        }
        errors, _tasks, mappings = task_pages.validate_crosswalk(
            self.data, crosswalk
        )
        self.assertEqual(errors, [])
        self.assertIn("one", mappings)

    def test_repository_crosswalk_only_names_catalog_tasks(self):
        import json

        data = json.loads((BUILD_DIR.parent / "dashboard" / "data.json").read_text())
        crosswalk = json.loads((BUILD_DIR / "task-pages.json").read_text())
        errors, _tasks, mappings = task_pages.validate_crosswalk(data, crosswalk)
        self.assertEqual(errors, [])
        self.assertGreaterEqual(len(mappings), 10)

    def test_task_index_parser_keeps_only_task_sections_and_deduplicates(self):
        html = """
        <html><body><main>
          <h2>Technical setup</h2>
          <a href="/one/">Do one</a><a href="/one#again">Duplicate</a>
          <h2>Frameworks &amp; Strategy (reference, not step-by-step tasks)</h2>
          <a href="/framework/">Reference only</a>
          <h2>Publish &amp; crosspost</h2>
          <a href="https://blitzmetrics.com/two/">Do two</a>
          <a href="https://other.example/foreign/">Foreign</a>
        </main></body></html>
        """
        links = task_pages.parse_task_index(
            html.encode("utf-8"), "text/html; charset=utf-8",
            "https://blitzmetrics.com/the-task-library/",
        )
        self.assertEqual([item["sourceUrl"] for item in links], [
            "https://blitzmetrics.com/one/",
            "https://blitzmetrics.com/two/",
        ])

    def test_source_index_inventory_surfaces_unmapped_live_task_pages(self):
        crosswalk = {
            "sourceIndex": "https://blitzmetrics.com/the-task-library/",
            "tasks": {
                "one": {
                    "url": "https://blitzmetrics.com/one/",
                    "matchMethod": "manual-content-review",
                }
            },
        }
        index_html = """
        <html><head><title>Task library</title></head><body><main>
          <h1>Task library</h1><h2>Technical setup</h2>
          <a href="/one/">One</a><a href="/unmapped/">Unmapped</a>
        </main></body></html>
        """

        def index_fetch(url, **_kwargs):
            html = index_html if url.endswith("the-task-library/") else good_html(url)
            return {
                "status": 200,
                "finalUrl": url,
                "redirectChain": [],
                "contentType": "text/html; charset=utf-8",
                "body": html.encode("utf-8"),
                "bodyTruncated": False,
                "durationMs": 1,
                "fetchError": None,
            }

        report = task_pages.build_report(self.data, crosswalk, fetcher=index_fetch)
        task_pages.attach_source_index_inventory(
            report, crosswalk, fetcher=index_fetch
        )
        inventory = report["sourceIndexInventory"]
        self.assertEqual(inventory["uniqueFinalTaskPages"], 2)
        self.assertEqual(inventory["mappedFinalTaskPages"], 1)
        self.assertEqual(inventory["unmappedFinalTaskPages"], 1)
        self.assertEqual(inventory["unmapped"][0]["label"], "Unmapped")
        self.assertEqual(task_pages.report_exit_code(report, strict=True), 0)


if __name__ == "__main__":
    unittest.main()
