#!/usr/bin/env python3
"""Audit contextual links among exact task pages, hubs, and methodology.

The graph is deliberately directional.  A task page should orient readers to
the Task Library and its broader definitive article when distinct; a hub should
link back down to a relevant exact task page.  A direct methodology link is
measured but is not required on every SOP because the Task Library already
provides that context and repeating it everywhere would become boilerplate.
Missing edges are an observation queue, not permission for sitewide link spam.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import urljoin, urlsplit


BUILD_DIR = Path(__file__).resolve().parent
if str(BUILD_DIR) not in sys.path:
    sys.path.insert(0, str(BUILD_DIR))

import audit_public_articles as public_audit
import audit_task_pages as task_pages


ROOT = BUILD_DIR.parent
DEFAULT_INPUT = ROOT / "dashboard" / "data.json"
DEFAULT_MAP = BUILD_DIR / "task-pages.json"
DEFAULT_OUTPUT = ROOT / "dashboard" / "internal-link-graph-audit.json"
DEFAULT_METHODOLOGY = "https://blitzmetrics.com/content-factory-ai-capability-index/"
LIBRARY_URLS = (
    "https://blitzmetrics.com/the-task-library/",
    "https://blitzmetrics.com/task-library-dashboard/",
)


class InternalLinkParser(HTMLParser):
    IGNORED = {"script", "style", "noscript", "svg", "template"}
    CHROME = {"nav", "header", "footer", "aside"}

    def __init__(self, base_url):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.ignore_depth = 0
        self.chrome_depth = 0
        self.body_depth = 0
        self.semantic_depth = 0
        self.semantic_seen = False
        self.anchor_url = None
        self.anchor_parts = []
        self.semantic_links = []
        self.body_links = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self.IGNORED:
            self.ignore_depth += 1
            return
        if self.ignore_depth:
            return
        if tag in self.CHROME:
            self.chrome_depth += 1
        if tag == "body":
            self.body_depth += 1
        if tag in {"main", "article"}:
            self.semantic_depth += 1
            self.semantic_seen = True
        attributes = {str(key).lower(): str(value or "") for key, value in attrs}
        href = attributes.get("href", "").strip()
        if tag == "a" and href and not self.chrome_depth:
            self.anchor_url = urljoin(self.base_url, href)
            self.anchor_parts = []

    def handle_data(self, data):
        if self.anchor_url and not self.ignore_depth:
            self.anchor_parts.append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.IGNORED:
            self.ignore_depth = max(0, self.ignore_depth - 1)
            return
        if self.ignore_depth:
            return
        if tag == "a" and self.anchor_url:
            item = {
                "url": self.anchor_url,
                "text": re.sub(r"\s+", " ", " ".join(self.anchor_parts)).strip()[:160],
            }
            if self.body_depth and not self.chrome_depth:
                self.body_links.append(item)
            if self.semantic_depth and not self.chrome_depth:
                self.semantic_links.append(item)
            self.anchor_url = None
            self.anchor_parts = []
        if tag in {"main", "article"}:
            self.semantic_depth = max(0, self.semantic_depth - 1)
        if tag == "body":
            self.body_depth = max(0, self.body_depth - 1)
        if tag in self.CHROME:
            self.chrome_depth = max(0, self.chrome_depth - 1)


def extract_links(body, content_type, base_url):
    text, _charset = public_audit.decode_body(body, content_type)
    parser = InternalLinkParser(base_url)
    parser.feed(text)
    candidates = parser.semantic_links if parser.semantic_links else parser.body_links
    links = []
    seen = set()
    for item in candidates:
        normalized, error = public_audit.normalize_article_url(item["url"])
        if error:
            continue
        host = public_audit.host_key(urlsplit(normalized).hostname)
        if host not in task_pages.TASK_PAGE_HOSTS:
            continue
        identity = public_audit.canonical_identity(normalized)
        if identity in seen:
            continue
        seen.add(identity)
        links.append({"url": normalized, "text": item["text"]})
    return links


def catalog_task_records(data, crosswalk):
    errors, _catalog, mappings = task_pages.validate_crosswalk(data, crosswalk)
    if errors:
        raise ValueError("; ".join(errors))
    records = []
    for category in data.get("categories", []):
        for task in category.get("tasks", []):
            slug = task.get("slug")
            mapping = mappings.get(slug)
            if not mapping:
                continue
            article = task.get("article") or None
            if isinstance(article, str):
                article, article_error = public_audit.normalize_article_url(article)
                if article_error:
                    article = None
            records.append({
                "slug": slug,
                "category": category.get("name"),
                "taskPage": mapping["url"],
                "definitiveArticle": article,
                "canonicalTask": mapping.get("canonicalTask"),
            })
    return records


def fetch_graph_page(url, config, fetcher):
    fetched = fetcher(
        url,
        timeout=config.timeout_seconds,
        max_bytes=config.max_body_bytes,
        user_agent=config.user_agent,
        allowed_source_hosts=task_pages.TASK_PAGE_HOSTS,
        allowed_redirect_hosts=task_pages.TASK_PAGE_HOSTS,
    )
    final_url = fetched.get("finalUrl") or url
    links = []
    if fetched.get("status") == 200 and not fetched.get("fetchError"):
        links = extract_links(
            fetched.get("body") or b"",
            fetched.get("contentType") or "",
            final_url,
        )
    return {
        "sourceUrl": url,
        "finalUrl": final_url,
        "status": fetched.get("status"),
        "fetchError": fetched.get("fetchError"),
        "links": links,
    }


def build_report(
    data, crosswalk, methodology_url=DEFAULT_METHODOLOGY,
    config=None, fetcher=public_audit.fetch_url,
):
    config = config or public_audit.AuditConfig(
        allowed_source_hosts=("localservicespotlight.com",),
        allowed_redirect_hosts=("localservicespotlight.com",),
    )
    records = catalog_task_records(data, crosswalk)
    node_urls = {methodology_url, *LIBRARY_URLS}
    for record in records:
        node_urls.add(record["taskPage"])
        if record["definitiveArticle"]:
            node_urls.add(record["definitiveArticle"])

    pages = []
    with ThreadPoolExecutor(max_workers=config.workers) as executor:
        futures = {
            executor.submit(fetch_graph_page, url, config, fetcher): url
            for url in sorted(node_urls)
        }
        for future in as_completed(futures):
            pages.append(future.result())
    pages.sort(key=lambda item: item["sourceUrl"])

    links_by_identity = {}
    page_by_identity = {}
    for page in pages:
        identities = {
            public_audit.canonical_identity(page["sourceUrl"]),
            public_audit.canonical_identity(page["finalUrl"]),
        }
        targets = {
            public_audit.canonical_identity(link["url"])
            for link in page["links"]
        }
        targets.discard(None)
        for identity in identities:
            if identity is not None:
                links_by_identity[identity] = targets
                page_by_identity[identity] = page

    def resolved_identity_from_identity(identity):
        page = page_by_identity.get(identity)
        if not page:
            return identity
        return public_audit.canonical_identity(page["finalUrl"]) or identity

    def resolved_identity(url):
        return resolved_identity_from_identity(public_audit.canonical_identity(url))

    def resolved_links(identity):
        return {
            resolved_identity_from_identity(target)
            for target in links_by_identity.get(identity, set())
        }

    library_identities = {resolved_identity(url) for url in LIBRARY_URLS}
    methodology_identity = resolved_identity(methodology_url)
    relationships = []
    for record in records:
        task_source_identity = public_audit.canonical_identity(record["taskPage"])
        hub_source_identity = public_audit.canonical_identity(record["definitiveArticle"])
        task_identity = resolved_identity(record["taskPage"])
        hub_identity = resolved_identity(record["definitiveArticle"])
        task_links = resolved_links(task_source_identity)
        hub_links = resolved_links(hub_source_identity) if hub_source_identity else set()
        same_page = bool(hub_identity and hub_identity == task_identity)
        to_library = bool(task_links & library_identities)
        to_methodology = methodology_identity in task_links
        to_hub = same_page or not hub_identity or hub_identity in task_links
        hub_to_task = same_page or not hub_identity or task_identity in hub_links
        complete = to_library and to_hub and hub_to_task
        relationships.append({
            **record,
            "sameTaskAndHubPage": same_page,
            "taskPageToLibrary": to_library,
            "taskPageToMethodology": to_methodology,
            "taskPageToDefinitiveArticle": to_hub,
            "definitiveArticleToTaskPage": hub_to_task,
            "completeContextLoop": complete,
            "taskPageFetchOk": bool(
                page_by_identity.get(task_source_identity, {}).get("status") == 200
                and not page_by_identity.get(task_source_identity, {}).get("fetchError")
            ),
        })

    count = len(relationships)
    def count_true(field):
        return sum(bool(item[field]) for item in relationships)

    return {
        "auditVersion": "1.0",
        "interpretation": (
            "Directional contextual-link coverage for reviewed exact task pages. "
            "Direct methodology links are measured but not required on every SOP; "
            "this is not a recommendation for boilerplate or sitewide insertion."
        ),
        "summary": {
            "mappedTaskRecords": count,
            "uniquePagesFetched": len(pages),
            "taskPageToLibrary": count_true("taskPageToLibrary"),
            "taskPageToMethodology": count_true("taskPageToMethodology"),
            "taskPageToDefinitiveArticle": count_true("taskPageToDefinitiveArticle"),
            "definitiveArticleToTaskPage": count_true("definitiveArticleToTaskPage"),
            "completeContextLoops": count_true("completeContextLoop"),
            "pageFetchFailures": sum(
                page.get("status") != 200 or bool(page.get("fetchError"))
                for page in pages
            ),
        },
        "relationships": relationships,
        "pages": pages,
    }


def report_exit_code(report, strict=False):
    summary = report.get("summary", {})
    incomplete = summary.get("completeContextLoops", 0) != summary.get(
        "mappedTaskRecords", 0
    )
    return 1 if strict and (summary.get("pageFetchFailures", 0) or incomplete) else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--map", dest="map_path", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--methodology-url", default=DEFAULT_METHODOLOGY)
    parser.add_argument("--timeout", type=float, default=public_audit.DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--workers", type=int, default=public_audit.DEFAULT_WORKERS)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        crosswalk = json.loads(args.map_path.read_text(encoding="utf-8"))
        config = public_audit.AuditConfig(
            timeout_seconds=args.timeout,
            workers=args.workers,
            allowed_source_hosts=("localservicespotlight.com",),
            allowed_redirect_hosts=("localservicespotlight.com",),
        )
        report = build_report(
            data, crosswalk, args.methodology_url, config=config
        )
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"internal-link graph audit failed: {exc}", file=sys.stderr)
        return 2
    summary = report["summary"]
    print(
        f"Context loops complete for {summary['completeContextLoops']}/"
        f"{summary['mappedTaskRecords']} mapped task records; "
        f"{summary['pageFetchFailures']} page fetch failures."
    )
    return report_exit_code(report, strict=args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
