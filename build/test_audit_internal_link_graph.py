#!/usr/bin/env python3

from pathlib import Path
import sys
import unittest


BUILD_DIR = Path(__file__).resolve().parent
if str(BUILD_DIR) not in sys.path:
    sys.path.insert(0, str(BUILD_DIR))

import audit_internal_link_graph as graph


def response(url, links):
    anchors = "".join(f'<a href="{href}">{text}</a>' for href, text in links)
    html = f"<html><body><nav><a href='/noise/'>Noise</a></nav><main>{anchors}</main></body></html>"
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


class InternalLinkGraphTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            "categories": [{
                "name": "Category",
                "tasks": [{
                    "slug": "one",
                    "article": "https://blitzmetrics.com/hub/",
                }],
            }]
        }
        self.crosswalk = {
            "tasks": {
                "one": {
                    "url": "https://blitzmetrics.com/task-one/",
                    "matchMethod": "manual-content-review",
                }
            }
        }

    def test_extract_links_uses_body_content_not_navigation(self):
        html = (
            "<html><body><nav><a href='/noise/'>Noise</a></nav><main>"
            "<a href='/kept/#part'>Kept</a></main></body></html>"
        )
        links = graph.extract_links(
            html.encode(), "text/html", "https://blitzmetrics.com/source/"
        )
        self.assertEqual(links, [{
            "url": "https://blitzmetrics.com/kept/",
            "text": "Kept",
        }])

    def test_complete_directional_loop_passes(self):
        methodology = graph.DEFAULT_METHODOLOGY
        pages = {
            "https://blitzmetrics.com/task-one/": [
                ("/the-task-library/", "Library"),
                ("/hub/", "Hub"),
                (methodology, "Method"),
            ],
            "https://blitzmetrics.com/hub/": [
                ("/task-one/", "Task"),
            ],
        }

        def fetch(url, **_kwargs):
            return response(url, pages.get(url, []))

        report = graph.build_report(
            self.data, self.crosswalk, fetcher=fetch
        )
        item = report["relationships"][0]
        self.assertTrue(item["completeContextLoop"])
        self.assertEqual(report["summary"]["completeContextLoops"], 1)
        self.assertEqual(graph.report_exit_code(report, strict=True), 0)

    def test_missing_methodology_and_backlink_are_visible(self):
        def fetch(url, **_kwargs):
            return response(url, [("/the-task-library/", "Library")])

        report = graph.build_report(
            self.data, self.crosswalk, fetcher=fetch
        )
        item = report["relationships"][0]
        self.assertTrue(item["taskPageToLibrary"])
        self.assertFalse(item["taskPageToMethodology"])
        self.assertFalse(item["definitiveArticleToTaskPage"])
        self.assertFalse(item["completeContextLoop"])
        self.assertEqual(graph.report_exit_code(report, strict=True), 1)


if __name__ == "__main__":
    unittest.main()
