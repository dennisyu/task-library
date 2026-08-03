#!/usr/bin/env python3
"""Audit the exact task-page layer without conflating it with topic hubs.

``build/task-pages.json`` is a reviewed crosswalk from stable task slugs to
public, task-specific SOP pages.  This command validates the crosswalk against
the generated catalog and reuses the bounded public-page auditor for HTTP,
redirect, content, login, and canonical checks.  The default is observational;
``--strict`` makes mapping or public-page findings fail the command.
"""

import argparse
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


ROOT = BUILD_DIR.parent
DEFAULT_INPUT = ROOT / "dashboard" / "data.json"
DEFAULT_MAP = BUILD_DIR / "task-pages.json"
DEFAULT_OUTPUT = ROOT / "dashboard" / "task-page-audit.json"
ALLOWED_ENTRY_FIELDS = {"url", "matchMethod", "canonicalTask"}
TASK_PAGE_HOSTS = {"blitzmetrics.com", "localservicespotlight.com"}
TASK_INDEX_SECTIONS = {
    "Technical setup",
    "Foundation · Access & Governance",
    "Capture & inventory SOPs",
    "Edit & transcribe",
    "Build the asset (article & library)",
    "Publish & crosspost",
    "Entity & authority distribution",
    "Boost & advertise",
    "Perform — measure what matters",
}


class TaskIndexParser(HTMLParser):
    """Collect body links grouped under task-like headings on the live index."""

    def __init__(self, base_url):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.semantic_depth = 0
        self.chrome_depth = 0
        self.heading_tag = None
        self.heading_parts = []
        self.current_section = ""
        self.anchor_url = None
        self.anchor_parts = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"main", "article"}:
            self.semantic_depth += 1
        if tag in {"nav", "header", "footer", "aside"}:
            self.chrome_depth += 1
        if self.semantic_depth and not self.chrome_depth and tag in {"h2", "h3", "h4"}:
            self.heading_tag = tag
            self.heading_parts = []
        attributes = {str(key).lower(): str(value or "") for key, value in attrs}
        href = attributes.get("href", "").strip()
        if self.semantic_depth and not self.chrome_depth and tag == "a" and href:
            self.anchor_url = urljoin(self.base_url, href)
            self.anchor_parts = []

    def handle_data(self, data):
        if self.heading_tag:
            self.heading_parts.append(data)
        if self.anchor_url:
            self.anchor_parts.append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == self.heading_tag:
            self.current_section = re.sub(
                r"\s+", " ", " ".join(self.heading_parts)
            ).strip()
            self.heading_tag = None
            self.heading_parts = []
        if tag == "a" and self.anchor_url:
            if self.current_section in TASK_INDEX_SECTIONS:
                self.links.append({
                    "section": self.current_section,
                    "sourceUrl": self.anchor_url,
                    "label": re.sub(r"\s+", " ", " ".join(self.anchor_parts)).strip(),
                })
            self.anchor_url = None
            self.anchor_parts = []
        if tag in {"main", "article"}:
            self.semantic_depth = max(0, self.semantic_depth - 1)
        if tag in {"nav", "header", "footer", "aside"}:
            self.chrome_depth = max(0, self.chrome_depth - 1)


def parse_task_index(body, content_type, base_url):
    text, _charset = public_audit.decode_body(body, content_type)
    parser = TaskIndexParser(base_url)
    parser.feed(text)
    output = []
    seen = set()
    for entry in parser.links:
        normalized, error = public_audit.normalize_article_url(entry["sourceUrl"])
        if (
            error
            or public_audit.host_key(urlsplit(normalized).hostname)
            not in TASK_PAGE_HOSTS
        ):
            continue
        identity = public_audit.canonical_identity(normalized)
        if identity in seen:
            continue
        seen.add(identity)
        output.append({**entry, "sourceUrl": normalized})
    return output


def catalog_tasks(data):
    tasks = []
    for category in data.get("categories", []):
        tasks.extend(category.get("tasks", []))
    return tasks


def validate_crosswalk(data, crosswalk):
    errors = []
    if not isinstance(crosswalk, dict):
        return ["task-page map must be a JSON object"], {}, {}
    entries = crosswalk.get("tasks")
    if not isinstance(entries, dict):
        return ['task-page map needs a "tasks" object'], {}, {}

    tasks = catalog_tasks(data)
    task_by_slug = {task.get("slug"): task for task in tasks if task.get("slug")}
    normalized = {}
    for slug, entry in entries.items():
        where = f"task-pages[{slug!r}]"
        if slug not in task_by_slug:
            errors.append(f"{where}: unknown catalog task")
        if not isinstance(entry, dict):
            errors.append(f"{where}: entry must be an object")
            continue
        extras = set(entry) - ALLOWED_ENTRY_FIELDS
        if extras:
            errors.append(f"{where}: unexpected fields {sorted(extras)}")
        url = entry.get("url")
        if not isinstance(url, str) or not url.strip():
            errors.append(f"{where}: url must be a non-empty string")
            continue
        normalized_url, url_error = public_audit.normalize_article_url(url)
        if url_error:
            errors.append(f"{where}: {url_error}")
            continue
        policy_error = public_audit.destination_policy_error(
            normalized_url, TASK_PAGE_HOSTS
        )
        if policy_error:
            errors.append(f"{where}: {policy_error}")
            continue
        method = entry.get("matchMethod")
        if not isinstance(method, str) or not method.strip():
            errors.append(f"{where}: matchMethod must be a non-empty string")
        canonical_task = entry.get("canonicalTask")
        if canonical_task is not None:
            if canonical_task == slug:
                errors.append(f"{where}: canonicalTask cannot reference itself")
            elif canonical_task not in task_by_slug:
                errors.append(f"{where}: canonicalTask is not a catalog task")
        normalized[slug] = {
            "url": normalized_url,
            "matchMethod": method,
            **({"canonicalTask": canonical_task} if canonical_task else {}),
        }

    return errors, task_by_slug, normalized


def build_report(data, crosswalk, config=None, fetcher=public_audit.fetch_url):
    config = config or public_audit.AuditConfig()
    errors, task_by_slug, mappings = validate_crosswalk(data, crosswalk)
    synthetic = {
        "tasks": [
            {"slug": slug, "article": entry["url"]}
            for slug, entry in sorted(mappings.items())
        ]
    }
    health = public_audit.audit_data(
        synthetic,
        config=config,
        fetcher=fetcher,
        input_label="build/task-pages.json",
    ) if mappings else {
        "summary": {
            "auditedUrls": 0,
            "cleanUrls": 0,
            "urlsWithBlockingFindings": 0,
            "blockingFindingCount": 0,
        },
        "results": [],
    }
    unique_pages = {
        public_audit.canonical_identity(entry["url"])
        for entry in mappings.values()
    }
    unique_pages.discard(None)
    alias_count = sum(bool(entry.get("canonicalTask")) for entry in mappings.values())
    total = len(task_by_slug)
    mapped = len(mappings)
    return {
        "auditVersion": "1.0",
        "reviewedAt": crosswalk.get("reviewedAt"),
        "sourceIndex": crosswalk.get("sourceIndex"),
        "interpretation": crosswalk.get("interpretation"),
        "mapping": {
            "catalogTasks": total,
            "mappedTaskRecords": mapped,
            "unmappedTaskRecords": max(0, total - mapped),
            "uniqueTaskPages": len(unique_pages),
            "legacyAliasRecords": alias_count,
            "errors": errors,
        },
        "taskPages": mappings,
        "publicHealth": health,
    }


def attach_source_index_inventory(
    report, crosswalk, config=None, fetcher=public_audit.fetch_url
):
    """Resolve task-like links from the live legacy index into a repair queue."""
    config = config or public_audit.AuditConfig()
    source_url = crosswalk.get("sourceIndex")
    if not isinstance(source_url, str) or not source_url.strip():
        report["sourceIndexInventory"] = {
            "sourceUrl": source_url,
            "error": "sourceIndex is missing",
        }
        return report
    normalized, error = public_audit.normalize_article_url(source_url)
    if error:
        report["sourceIndexInventory"] = {"sourceUrl": source_url, "error": error}
        return report
    index_fetch = fetcher(
        normalized,
        timeout=config.timeout_seconds,
        max_bytes=config.max_body_bytes,
        user_agent=config.user_agent,
        allowed_source_hosts=TASK_PAGE_HOSTS,
        allowed_redirect_hosts=TASK_PAGE_HOSTS,
    )
    if index_fetch.get("fetchError") or index_fetch.get("status") != 200:
        report["sourceIndexInventory"] = {
            "sourceUrl": normalized,
            "error": index_fetch.get("fetchError") or f"HTTP {index_fetch.get('status')}",
        }
        return report
    links = parse_task_index(
        index_fetch.get("body") or b"",
        index_fetch.get("contentType") or "",
        index_fetch.get("finalUrl") or normalized,
    )
    synthetic = {
        "tasks": [
            {"slug": f"legacy-index-{index:03d}", "article": entry["sourceUrl"]}
            for index, entry in enumerate(links, 1)
        ]
    }
    link_health = public_audit.audit_data(
        synthetic,
        config=config,
        fetcher=fetcher,
        input_label=normalized,
    )
    result_by_source = {
        public_audit.canonical_identity(result["sourceUrl"]): result
        for result in link_health.get("results", [])
    }
    mapped_identities = {
        public_audit.canonical_identity(entry["url"])
        for entry in report.get("taskPages", {}).values()
    }
    mapped_identities.discard(None)
    resolved = []
    for entry in links:
        result = result_by_source.get(public_audit.canonical_identity(entry["sourceUrl"]))
        final_url = result.get("finalUrl") if result else entry["sourceUrl"]
        final_identity = public_audit.canonical_identity(final_url)
        resolved.append({
            **entry,
            "finalUrl": final_url,
            "mappedToCurrentCatalog": final_identity in mapped_identities,
            "findings": result.get("findings", []) if result else [],
        })
    final_identities = {
        public_audit.canonical_identity(entry["finalUrl"])
        for entry in resolved
    }
    final_identities.discard(None)
    mapped_final = {
        public_audit.canonical_identity(entry["finalUrl"])
        for entry in resolved if entry["mappedToCurrentCatalog"]
    }
    mapped_final.discard(None)
    report["sourceIndexInventory"] = {
        "sourceUrl": normalized,
        "taskLikeLinks": len(links),
        "uniqueFinalTaskPages": len(final_identities),
        "mappedFinalTaskPages": len(mapped_final),
        "unmappedFinalTaskPages": len(final_identities - mapped_final),
        "healthSummary": link_health.get("summary", {}),
        "unmapped": [entry for entry in resolved if not entry["mappedToCurrentCatalog"]],
    }
    return report


def report_exit_code(report, strict=False):
    mapping_errors = report.get("mapping", {}).get("errors", [])
    blocking = report.get("publicHealth", {}).get("summary", {}).get(
        "urlsWithBlockingFindings", 0
    )
    inventory = report.get("sourceIndexInventory", {})
    inventory_blocking = inventory.get("healthSummary", {}).get(
        "urlsWithBlockingFindings", 0
    )
    inventory_error = inventory.get("error")
    return 1 if strict and (
        mapping_errors or blocking or inventory_blocking or inventory_error
    ) else 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--map", dest="map_path", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=public_audit.DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--workers", type=int, default=public_audit.DEFAULT_WORKERS)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        crosswalk = json.loads(args.map_path.read_text(encoding="utf-8"))
        config = public_audit.AuditConfig(
            timeout_seconds=args.timeout,
            workers=args.workers,
            allowed_source_hosts=("localservicespotlight.com",),
            allowed_redirect_hosts=("localservicespotlight.com",),
        )
        report = build_report(data, crosswalk, config=config)
        attach_source_index_inventory(report, crosswalk, config=config)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"task-page audit setup failed: {exc}", file=sys.stderr)
        return 2
    summary = report["publicHealth"]["summary"]
    mapping = report["mapping"]
    inventory = report.get("sourceIndexInventory", {})
    print(
        f"Mapped {mapping['mappedTaskRecords']}/{mapping['catalogTasks']} task records "
        f"to {mapping['uniqueTaskPages']} exact pages; "
        f"{summary.get('cleanUrls', 0)}/{summary.get('auditedUrls', 0)} pages clean; "
        f"legacy index has {inventory.get('unmappedFinalTaskPages', '?')} unmapped task-like pages."
    )
    for error in mapping["errors"]:
        print(f"mapping: {error}", file=sys.stderr)
    return report_exit_code(report, strict=args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
