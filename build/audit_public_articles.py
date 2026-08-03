#!/usr/bin/env python3
"""Audit the public articles referenced by the built Task Library catalog.

The default mode is observational: findings are written to JSON and the process
exits zero. ``--strict`` exits one when at least one blocking finding is present.
Invalid arguments, unreadable input, and unwritable output exit two.
"""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import ipaddress
import json
from pathlib import Path
import re
import socket
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "dashboard" / "data.json"
DEFAULT_BASE_URL = "https://blitzmetrics.com/"
DEFAULT_TIMEOUT_SECONDS = 12.0
DEFAULT_WORKERS = 6
MAX_WORKERS = 16
DEFAULT_MAX_BODY_BYTES = 2_000_000
MAX_BODY_BYTES = 10_000_000
DEFAULT_MIN_CONTENT_WORDS = 80
DEFAULT_MIN_CONTENT_CHARS = 400
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
AUDIT_HEADER_VALUE = (
    "1.0; https://github.com/Goodrich-Dev/task-library"
)

WORD_RE = re.compile(r"\b[\w'-]+\b", re.UNICODE)
LOGIN_PATH_RE = re.compile(
    r"(?:^|/)(?:wp-login\.php|log-?in|sign-?in|auth(?:enticate|entication)?)(?:/|$)",
    re.IGNORECASE,
)
LOGIN_TITLE_RE = re.compile(
    r"^(?:log\s*in|sign\s*in|authentication required|authorization required)\b",
    re.IGNORECASE,
)
ERROR_CODE_RE = re.compile(r"^(?:4(?:03|04)|5(?:00|02|03|04))(?:\b|\s*[-:|])")
ERROR_PHRASES = (
    "page not found",
    "access denied",
    "forbidden",
    "internal server error",
    "service unavailable",
    "gateway timeout",
    "maintenance mode",
    "site is experiencing technical difficulties",
)
SENSITIVE_QUERY_KEYS = {
    "access-token",
    "accesstoken",
    "api-key",
    "apikey",
    "auth",
    "authorization",
    "authorization-code",
    "awsaccesskeyid",
    "credential",
    "googleaccessid",
    "jwt",
    "key-pair-id",
    "password",
    "passwd",
    "policy",
    "secret",
    "session",
    "sessionid",
    "sig",
    "signature",
    "token",
}


@dataclass(frozen=True)
class AuditConfig:
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    workers: int = DEFAULT_WORKERS
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES
    min_content_words: int = DEFAULT_MIN_CONTENT_WORDS
    min_content_chars: int = DEFAULT_MIN_CONTENT_CHARS
    user_agent: str = DEFAULT_USER_AGENT
    allowed_source_hosts: tuple = ()
    allowed_redirect_hosts: tuple = ()


class BlockedDestinationError(RuntimeError):
    """Raised before a request when a source or redirect violates fetch policy."""

    def __init__(self, url, reason):
        super().__init__(reason)
        self.url = url
        self.reason = reason


class RecordingRedirectHandler(HTTPRedirectHandler):
    """Follow normal urllib redirects while retaining a minimal redirect chain."""

    def __init__(self, allowed_hosts, resolver=socket.getaddrinfo):
        super().__init__()
        self.history = []
        self.allowed_hosts = set(allowed_hosts)
        self.resolver = resolver

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        destination = urljoin(req.full_url, newurl)
        entry = {
            "from": redact_sensitive_url(req.full_url),
            "to": redact_sensitive_url(destination),
            "status": code,
            "followed": False,
        }
        try:
            validate_destination(destination, self.allowed_hosts, self.resolver)
        except BlockedDestinationError as exc:
            entry["blockedReason"] = exc.reason
            self.history.append(entry)
            raise
        entry["followed"] = True
        self.history.append(entry)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class PublicTextParser(HTMLParser):
    """Extract page-content signals without retaining or emitting page bodies."""

    IGNORED = {"script", "style", "noscript", "svg", "template"}
    CHROME = {"nav", "header", "footer", "aside"}
    SEMANTIC = {"main", "article"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ignore_depth = 0
        self.chrome_depth = 0
        self.body_depth = 0
        self.semantic_depth = 0
        self.title_depth = 0
        self.heading_depth = 0
        self.all_parts = []
        self.body_parts = []
        self.semantic_parts = []
        self.title_parts = []
        self.heading_parts = []
        self.heading_count = 0
        self.h1_count = 0
        self.password_input_count = 0
        self.has_semantic_region = False
        self.canonical_hrefs = []

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
        if tag in self.SEMANTIC:
            self.semantic_depth += 1
            self.has_semantic_region = True
        if tag == "title":
            self.title_depth += 1
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.heading_depth += 1
            self.heading_count += 1
            if tag == "h1":
                self.h1_count += 1
        if tag == "input":
            attributes = {str(key).lower(): str(value or "").lower() for key, value in attrs}
            if attributes.get("type") == "password":
                self.password_input_count += 1
        if tag == "link":
            attributes = {str(key).lower(): str(value or "") for key, value in attrs}
            rel_tokens = {token.lower() for token in attributes.get("rel", "").split()}
            href = attributes.get("href", "").strip()
            if "canonical" in rel_tokens and href:
                self.canonical_hrefs.append(href)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.IGNORED:
            self.ignore_depth = max(0, self.ignore_depth - 1)
            return
        if self.ignore_depth:
            return
        if tag in self.CHROME:
            self.chrome_depth = max(0, self.chrome_depth - 1)
        if tag == "body":
            self.body_depth = max(0, self.body_depth - 1)
        if tag in self.SEMANTIC:
            self.semantic_depth = max(0, self.semantic_depth - 1)
        if tag == "title":
            self.title_depth = max(0, self.title_depth - 1)
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.heading_depth = max(0, self.heading_depth - 1)

    def handle_data(self, data):
        if self.ignore_depth or not data.strip():
            return
        self.all_parts.append(data)
        if self.title_depth:
            self.title_parts.append(data)
        if self.heading_depth:
            self.heading_parts.append(data)
        if self.body_depth and not self.chrome_depth:
            self.body_parts.append(data)
        if self.semantic_depth and not self.chrome_depth:
            self.semantic_parts.append(data)


def compact_text(parts):
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def host_key(value):
    """Compare hosts exactly except for a leading ``www.`` convenience alias."""
    if not value:
        return ""
    candidate = value.strip().lower()
    if "://" in candidate:
        candidate = urlsplit(candidate).hostname or ""
    else:
        try:
            candidate = urlsplit("//" + candidate.split("/", 1)[0]).hostname or ""
        except ValueError:
            return ""
    candidate = candidate.rstrip(".")
    return candidate[4:] if candidate.startswith("www.") else candidate


def sensitive_query_keys(url):
    keys = []
    try:
        pairs = parse_qsl(urlsplit(url).query, keep_blank_values=True)
    except ValueError:
        return ["<invalid-query>"]
    for raw_key, _value in pairs:
        key = raw_key.strip().lower().replace("_", "-")
        if (
            key in SENSITIVE_QUERY_KEYS
            or key.startswith("x-amz-")
            or key.startswith("x-goog-")
            or key.endswith("-token")
            or key.endswith("-secret")
            or key.endswith("-signature")
            or key.endswith("-credential")
        ):
            keys.append(raw_key)
    return sorted(set(keys), key=str.lower)


def redact_sensitive_url(url):
    """Preserve a blocked Location while removing credential-like query values."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<invalid-url>"
    sensitive = {key.lower() for key in sensitive_query_keys(url)}
    if not sensitive:
        return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    redacted = [
        (key, "<redacted>" if key.lower() in sensitive else value)
        for key, value in pairs
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(redacted), ""))


def destination_policy_error(url, allowed_hosts):
    """Perform checks that do not require DNS or an outbound connection."""
    try:
        parts = urlsplit(url)
        hostname = parts.hostname
        _port = parts.port
    except ValueError as exc:
        return f"invalid destination URL: {exc}"
    if any(character.isspace() for character in url):
        return "destination URL contains whitespace"
    if parts.scheme.lower() not in {"http", "https"} or not hostname:
        return "destination must use HTTP(S) and include a host"
    if parts.username or parts.password:
        return "destination must not include credentials"
    secret_keys = sensitive_query_keys(url)
    if secret_keys:
        return "destination contains sensitive query key(s): " + ", ".join(secret_keys)
    if host_key(hostname) not in {host_key(host) for host in allowed_hosts}:
        return f"destination host {hostname} is not explicitly allowed"
    try:
        literal = ipaddress.ip_address(hostname.rstrip("."))
    except ValueError:
        literal = None
    if literal is not None and not literal.is_global:
        return f"destination IP {literal} is not globally routable"
    return None


def validate_destination(url, allowed_hosts, resolver=socket.getaddrinfo):
    """Reject unapproved or non-public destinations before urllib opens them."""
    error = destination_policy_error(url, allowed_hosts)
    if error:
        raise BlockedDestinationError(url, error)
    parts = urlsplit(url)
    hostname = parts.hostname.rstrip(".")
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        return [str(literal)]
    port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
    try:
        answers = resolver(hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise BlockedDestinationError(url, f"DNS resolution failed: {exc}") from exc
    addresses = []
    for answer in answers:
        try:
            address = answer[4][0].split("%", 1)[0]
            parsed = ipaddress.ip_address(address)
        except (IndexError, ValueError, TypeError):
            raise BlockedDestinationError(url, "DNS returned an invalid address")
        if not parsed.is_global:
            raise BlockedDestinationError(
                url, f"DNS resolved to non-public address {parsed}"
            )
        addresses.append(str(parsed))
    if not addresses:
        raise BlockedDestinationError(url, "DNS returned no addresses")
    return sorted(set(addresses))


def normalize_article_url(value, base_url=DEFAULT_BASE_URL):
    """Return ``(normalized_url, error)`` for an absolute or root-relative URL."""
    if not isinstance(value, str) or not value.strip():
        return None, "article URL is empty"
    raw = value.strip()
    if raw.startswith("/"):
        raw = urljoin(base_url, raw)
    elif not re.match(r"^https?://", raw, re.IGNORECASE):
        return None, "article URL must be HTTP(S) or root-relative"
    if any(char.isspace() for char in raw):
        return None, "article URL contains whitespace"
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError as exc:
        return None, f"invalid article URL: {exc}"
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        return None, "article URL must include an HTTP(S) host"
    if parts.username or parts.password:
        return None, "article URL must not include credentials"
    secret_keys = sensitive_query_keys(raw)
    if secret_keys:
        return None, "article URL contains sensitive query key(s): " + ", ".join(secret_keys)

    scheme = parts.scheme.lower()
    hostname = parts.hostname.lower()
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = hostname if port is None or default_port else f"{hostname}:{port}"
    # Preserve the request path exactly. A trailing slash can be operationally
    # significant even when it denotes the same canonical resource: some WAFs
    # reject the non-canonical variant instead of redirecting it.
    path = parts.path or "/"
    return urlunsplit((scheme, netloc, path, parts.query, "")), None


def source_allowed_hosts(config):
    base_host = urlsplit(config.base_url).hostname or ""
    return {host_key(base_host), *(host_key(host) for host in config.allowed_source_hosts)}


def redirect_allowed_hosts(source_url, config):
    return {
        host_key(urlsplit(source_url).hostname),
        *(host_key(host) for host in config.allowed_redirect_hosts),
    }


def iter_catalog_tasks(data):
    """Yield tasks from current category-shaped data and legacy top-level forms."""
    if not isinstance(data, dict):
        return
    top_tasks = data.get("tasks")
    if isinstance(top_tasks, dict):
        yield from (task for task in top_tasks.values() if isinstance(task, dict))
    elif isinstance(top_tasks, list):
        yield from (task for task in top_tasks if isinstance(task, dict))
    categories = data.get("categories")
    if isinstance(categories, list):
        for category in categories:
            if not isinstance(category, dict):
                continue
            tasks = category.get("tasks")
            if isinstance(tasks, list):
                yield from (task for task in tasks if isinstance(task, dict))


def collect_targets(data, base_url=DEFAULT_BASE_URL, allowed_source_hosts=()):
    """Deduplicate article URLs while retaining every referencing task slug."""
    targets = {}
    base_host = urlsplit(base_url).hostname or ""
    source_hosts = {host_key(base_host), *(host_key(host) for host in allowed_source_hosts)}
    tasks_seen = 0
    tasks_with_article = 0
    tasks_without_article = 0
    for index, task in enumerate(iter_catalog_tasks(data) or []):
        tasks_seen += 1
        raw_url = task.get("article")
        if not isinstance(raw_url, str) or not raw_url.strip() or raw_url.strip().upper().startswith("GAP"):
            tasks_without_article += 1
            continue
        tasks_with_article += 1
        slug = str(task.get("slug") or task.get("title") or f"unnamed-{index + 1}")
        normalized, error = normalize_article_url(raw_url, base_url)
        policy_error = destination_policy_error(normalized, source_hosts) if normalized else None
        key = canonical_identity(normalized) if normalized else f"invalid:{raw_url.strip()}"
        displayed_source = normalized or redact_sensitive_url(raw_url.strip())
        target = targets.setdefault(
            key,
            {
                "sourceUrl": displayed_source,
                "sourceVariants": set(),
                "taskSlugs": set(),
                "urlValid": normalized is not None,
                "urlError": error,
                "fetchAllowed": normalized is not None and policy_error is None,
                "sourcePolicyError": policy_error,
            },
        )
        target["sourceVariants"].add(redact_sensitive_url(raw_url.strip()))
        target["taskSlugs"].add(slug)

    output = []
    for target in targets.values():
        target["sourceVariants"] = sorted(target["sourceVariants"])
        target["taskSlugs"] = sorted(target["taskSlugs"])
        target["taskCount"] = len(target["taskSlugs"])
        output.append(target)
    output.sort(key=lambda item: item["sourceUrl"])
    inventory = {
        "tasksSeen": tasks_seen,
        "tasksWithArticle": tasks_with_article,
        "tasksWithoutArticle": tasks_without_article,
        "uniqueArticleUrls": len(output),
        "duplicateArticleReferences": max(0, tasks_with_article - len(output)),
        "invalidArticleUrls": sum(not target["urlValid"] for target in output),
        "blockedSourceUrls": sum(
            target["urlValid"] and not target["fetchAllowed"] for target in output
        ),
    }
    return output, inventory


def _read_response(response, max_bytes):
    body = response.read(max_bytes + 1)
    if isinstance(body, str):
        body = body.encode("utf-8")
    truncated = len(body) > max_bytes
    return body[:max_bytes], truncated


def fetch_url(
    url,
    *,
    timeout,
    max_bytes,
    user_agent,
    allowed_source_hosts,
    allowed_redirect_hosts=(),
    resolver=socket.getaddrinfo,
    opener_factory=None,
):
    """Perform one bounded GET. The opener has no cookie jar by design."""
    started = time.monotonic()
    try:
        validate_destination(url, allowed_source_hosts, resolver)
    except BlockedDestinationError as exc:
        return {
            "status": None,
            "finalUrl": redact_sensitive_url(url),
            "redirectChain": [],
            "contentType": "",
            "body": b"",
            "bodyTruncated": False,
            "durationMs": round((time.monotonic() - started) * 1000, 1),
            "fetchError": {
                "type": "BlockedSourceDestination",
                "message": exc.reason,
            },
        }
    redirect_hosts = {
        host_key(urlsplit(url).hostname),
        *(host_key(host) for host in allowed_redirect_hosts),
    }
    redirect_handler = RecordingRedirectHandler(redirect_hosts, resolver)
    opener = (
        opener_factory(redirect_handler)
        if opener_factory is not None
        else build_opener(redirect_handler)
    )
    request = Request(
        url,
        method="GET",
        headers={
            "User-Agent": user_agent,
            # Identify the health check without using the custom bot UA that
            # the site's WAF rejects on otherwise healthy public articles.
            "X-Task-Library-Audit": AUDIT_HEADER_VALUE,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
        },
    )
    response = None
    try:
        try:
            response = opener.open(request, timeout=timeout)
        except HTTPError as exc:
            response = exc
        body, truncated = _read_response(response, max_bytes)
        headers = response.headers
        content_type = headers.get("Content-Type", "") if headers else ""
        status = getattr(response, "status", None) or response.getcode()
        return {
            "status": int(status) if status is not None else None,
            "finalUrl": redact_sensitive_url(response.geturl() or url),
            "redirectChain": list(redirect_handler.history),
            "contentType": content_type,
            "body": body,
            "bodyTruncated": truncated,
            "durationMs": round((time.monotonic() - started) * 1000, 1),
            "fetchError": None,
        }
    except BlockedDestinationError as exc:
        return {
            "status": redirect_handler.history[-1]["status"] if redirect_handler.history else None,
            "finalUrl": redact_sensitive_url(url),
            "redirectChain": list(redirect_handler.history),
            "contentType": "",
            "body": b"",
            "bodyTruncated": False,
            "durationMs": round((time.monotonic() - started) * 1000, 1),
            "fetchError": {"type": "BlockedRedirectDestination", "message": exc.reason},
        }
    except (URLError, TimeoutError, OSError) as exc:
        return {
            "status": None,
            "finalUrl": url,
            "redirectChain": list(redirect_handler.history),
            "contentType": "",
            "body": b"",
            "bodyTruncated": False,
            "durationMs": round((time.monotonic() - started) * 1000, 1),
            "fetchError": {"type": type(exc).__name__, "message": str(exc)},
        }
    finally:
        if response is not None:
            response.close()


def decode_body(body, content_type):
    match = re.search(r"charset\s*=\s*['\"]?([^\s;'\"]+)", content_type or "", re.I)
    charset = match.group(1) if match else "utf-8"
    try:
        return body.decode(charset, errors="replace"), charset
    except LookupError:
        return body.decode("utf-8", errors="replace"), "utf-8"


def looks_like_html(body, content_type):
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    if media_type in {"text/html", "application/xhtml+xml"}:
        return True
    prefix = body[:512].lstrip().lower()
    return prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html")


def page_signals(body, content_type):
    text, charset = decode_body(body, content_type)
    parser = PublicTextParser()
    parser.feed(text)
    semantic = compact_text(parser.semantic_parts)
    body_text = compact_text(parser.body_parts)
    document = compact_text(parser.all_parts)
    if semantic:
        selected, selector = semantic, "main/article"
    elif body_text:
        selected, selector = body_text, "body-minus-chrome"
    else:
        selected, selector = document, "document"
    title = compact_text(parser.title_parts)
    headings = compact_text(parser.heading_parts)
    return {
        "charset": charset,
        "title": title,
        "titleChars": len(title),
        "contentSelector": selector,
        "contentChars": len(selected),
        "contentWords": len(WORD_RE.findall(selected)),
        "documentChars": len(document),
        "documentWords": len(WORD_RE.findall(document)),
        "hasMainOrArticle": parser.has_semantic_region,
        "headingCount": parser.heading_count,
        "h1Count": parser.h1_count,
        "headingSample": headings[:240],
        "passwordInputCount": parser.password_input_count,
        "canonicalHrefs": list(parser.canonical_hrefs),
    }


def canonical_identity(url):
    """Compare the public resource identity, ignoring fragments and query tracking."""
    normalized, error = normalize_article_url(url)
    if error:
        return None
    parts = urlsplit(normalized)
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return (parts.scheme.lower(), host_key(parts.hostname), path)


def canonical_signals(final_url, hrefs):
    captured = []
    for href in hrefs:
        absolute = urljoin(final_url, href.strip())
        normalized, error = normalize_article_url(absolute)
        captured.append(
            {
                "url": normalized or redact_sensitive_url(absolute),
                "valid": normalized is not None,
                "error": error,
            }
        )
    return {
        "count": len(hrefs),
        "links": captured,
        "matchesFinal": bool(
            len(captured) == 1
            and captured[0]["valid"]
            and canonical_identity(captured[0]["url"]) == canonical_identity(final_url)
        ),
    }


def _soft_error_signals(title, heading_sample):
    signals = []
    for location, value in (("title", title), ("heading", heading_sample)):
        normalized = value.strip().lower()
        if not normalized:
            continue
        if ERROR_CODE_RE.search(normalized):
            signals.append(f"{location}:http-error-code")
        for phrase in ERROR_PHRASES:
            if phrase in normalized:
                signals.append(f"{location}:{phrase}")
    return sorted(set(signals))


def _login_signals(final_url, signals):
    found = []
    path = urlsplit(final_url).path
    if LOGIN_PATH_RE.search(path):
        found.append("url:login-path")
    title_login = bool(LOGIN_TITLE_RE.search(signals.get("title", "")))
    heading_login = bool(LOGIN_TITLE_RE.search(signals.get("headingSample", "")))
    if title_login:
        found.append("title:login-language")
    if heading_login:
        found.append("heading:login-language")
    if signals.get("passwordInputCount", 0) > 0 and (
        found or title_login or heading_login
    ):
        found.append("html:password-input")
    return found


def _finding(code, message, severity="error"):
    return {"code": code, "severity": severity, "message": message}


def analyze_target(target, fetch, config):
    findings = []
    source_url = target["sourceUrl"]
    if not target["urlValid"]:
        findings.append(_finding("invalid-article-url", target["urlError"]))
        return {
            "sourceUrl": source_url,
            "sourceVariants": target["sourceVariants"],
            "taskSlugs": target["taskSlugs"],
            "taskCount": target["taskCount"],
            "finalUrl": None,
            "status": None,
            "redirect": {"followed": False, "chain": [], "unexpectedHosts": []},
            "response": None,
            "contentSignals": None,
            "fetchError": None,
            "findings": findings,
        }
    if not target.get("fetchAllowed", True):
        findings.append(_finding("blocked-source-host", target["sourcePolicyError"]))
        return {
            "sourceUrl": source_url,
            "sourceVariants": target["sourceVariants"],
            "taskSlugs": target["taskSlugs"],
            "taskCount": target["taskCount"],
            "finalUrl": None,
            "status": None,
            "redirect": {"followed": False, "chain": [], "unexpectedHosts": []},
            "response": None,
            "contentSignals": None,
            "fetchError": None,
            "findings": findings,
        }

    fetch_error = fetch.get("fetchError")
    final_url = fetch.get("finalUrl") or source_url
    redirect_chain = fetch.get("redirectChain") or []
    if fetch_error:
        findings.append(
            _finding(
                "fetch-error",
                f"{fetch_error.get('type', 'network error')}: {fetch_error.get('message', '')}".strip(),
            )
        )
        if str(fetch_error.get("type", "")).startswith("Blocked"):
            findings.append(
                _finding("blocked-fetch-destination", fetch_error.get("message", "Blocked."))
            )

    status = fetch.get("status")
    if isinstance(status, int) and status >= 400:
        findings.append(_finding("http-error-status", f"Public GET returned HTTP {status}."))
    elif isinstance(status, int) and 300 <= status < 400:
        findings.append(
            _finding("unresolved-redirect-status", f"Public GET ended at HTTP {status}.")
        )
    elif status is None and not fetch_error:
        findings.append(_finding("missing-http-status", "The fetch returned no HTTP status."))

    allowed_hosts = {host_key(urlsplit(source_url).hostname)}
    allowed_hosts.update(host_key(host) for host in config.allowed_redirect_hosts)
    redirect_destinations = [step.get("to") for step in redirect_chain if step.get("to")]
    redirect_destinations.append(final_url)
    unexpected_hosts = sorted(
        {
            urlsplit(destination).hostname or ""
            for destination in redirect_destinations
            if host_key(urlsplit(destination).hostname) not in allowed_hosts
        }
    )
    if unexpected_hosts:
        findings.append(
            _finding(
                "unexpected-cross-site-redirect",
                "Redirect left the source host for: " + ", ".join(unexpected_hosts),
            )
        )
    blocked_redirects = [step for step in redirect_chain if step.get("blockedReason")]
    if blocked_redirects:
        locations = ", ".join(step["to"] for step in blocked_redirects)
        findings.append(
            _finding(
                "blocked-redirect-destination",
                "Redirect was recorded but not followed: " + locations,
            )
        )

    body = fetch.get("body") or b""
    if isinstance(body, str):
        body = body.encode("utf-8")
    content_type = fetch.get("contentType") or ""
    is_html = looks_like_html(body, content_type)
    signals = page_signals(body, content_type) if is_html else None
    if status is not None and not is_html:
        findings.append(
            _finding(
                "non-html-response",
                f"Expected a public article but received {content_type or 'an unknown content type'}.",
            )
        )
    if signals:
        canonical = canonical_signals(final_url, signals.pop("canonicalHrefs"))
        signals["canonical"] = canonical
        login_signals = _login_signals(final_url, signals)
        if login_signals:
            findings.append(
                _finding("login-page", "Login signals: " + ", ".join(login_signals))
            )
        error_signals = _soft_error_signals(signals["title"], signals["headingSample"])
        if error_signals:
            findings.append(
                _finding("error-page", "Soft error signals: " + ", ".join(error_signals))
            )
        if status == 200 and not login_signals and not error_signals:
            if canonical["count"] == 0:
                findings.append(
                    _finding(
                        "missing-canonical",
                        "No <link rel=canonical> was found on the final HTML page.",
                        severity="warning",
                    )
                )
            elif canonical["count"] > 1:
                findings.append(
                    _finding(
                        "multiple-canonicals",
                        f"Found {canonical['count']} canonical links; expected exactly one.",
                    )
                )
            else:
                link = canonical["links"][0]
                if not link["valid"]:
                    findings.append(
                        _finding("invalid-canonical", link["error"] or "Canonical URL is invalid.")
                    )
                else:
                    canonical_host = host_key(urlsplit(link["url"]).hostname)
                    final_host = host_key(urlsplit(final_url).hostname)
                    if canonical_host != final_host:
                        findings.append(
                            _finding(
                                "cross-host-canonical",
                                f"Canonical host {canonical_host} does not match final host {final_host}.",
                            )
                        )
                    elif not canonical["matchesFinal"]:
                        findings.append(
                            _finding(
                                "non-final-canonical",
                                "Canonical scheme/path does not match the final public URL.",
                            )
                        )
        if (
            signals["contentWords"] < config.min_content_words
            and signals["contentChars"] < config.min_content_chars
        ):
            findings.append(
                _finding(
                    "effectively-empty-body",
                    "Selected content has "
                    f"{signals['contentWords']} words/{signals['contentChars']} characters; "
                    "both are below the configured minimums of "
                    f"{config.min_content_words} words/{config.min_content_chars} characters.",
                )
            )
    if fetch.get("bodyTruncated"):
        findings.append(
            _finding(
                "response-body-truncated",
                f"Inspection stopped after {config.max_body_bytes} bytes.",
                severity="warning",
            )
        )

    redirected = (
        any(step.get("followed", True) for step in redirect_chain)
        or final_url != source_url
    )
    return {
        "sourceUrl": source_url,
        "sourceVariants": target["sourceVariants"],
        "taskSlugs": target["taskSlugs"],
        "taskCount": target["taskCount"],
        "finalUrl": final_url,
        "status": status,
        "redirect": {
            "followed": redirected,
            "chain": redirect_chain,
            "unexpectedHosts": unexpected_hosts,
        },
        "response": {
            "contentType": content_type,
            "bodyBytesInspected": len(body),
            "bodyTruncated": bool(fetch.get("bodyTruncated")),
            "durationMs": fetch.get("durationMs"),
        },
        "contentSignals": signals,
        "fetchError": fetch_error,
        "findings": findings,
    }


def summarize(results):
    codes = Counter()
    status_buckets = Counter()
    blocking_results = 0
    warning_results = 0
    for result in results:
        has_error = False
        has_warning = False
        for finding in result["findings"]:
            codes[finding["code"]] += 1
            has_error = has_error or finding["severity"] == "error"
            has_warning = has_warning or finding["severity"] == "warning"
        blocking_results += int(has_error)
        warning_results += int(has_warning)
        status = result.get("status")
        if status is None:
            status_buckets["none"] += 1
        else:
            status_buckets[f"{status // 100}xx"] += 1
    return {
        "auditedUrls": len(results),
        "cleanUrls": sum(not result["findings"] for result in results),
        "urlsWithBlockingFindings": blocking_results,
        "urlsWithWarnings": warning_results,
        "blockingFindingCount": sum(
            finding["severity"] == "error"
            for result in results
            for finding in result["findings"]
        ),
        "warningFindingCount": sum(
            finding["severity"] == "warning"
            for result in results
            for finding in result["findings"]
        ),
        "findingCounts": dict(sorted(codes.items())),
        "statusBuckets": dict(sorted(status_buckets.items())),
    }


def audit_data(data, config=None, fetcher=fetch_url, input_label="dashboard/data.json"):
    config = config or AuditConfig()
    targets, inventory = collect_targets(
        data, config.base_url, config.allowed_source_hosts
    )
    fetched = {}
    valid_targets = [
        target for target in targets if target["urlValid"] and target["fetchAllowed"]
    ]
    if valid_targets:
        with ThreadPoolExecutor(max_workers=min(config.workers, len(valid_targets))) as pool:
            future_targets = {
                pool.submit(
                    fetcher,
                    target["sourceUrl"],
                    timeout=config.timeout_seconds,
                    max_bytes=config.max_body_bytes,
                    user_agent=config.user_agent,
                    allowed_source_hosts=source_allowed_hosts(config),
                    allowed_redirect_hosts=redirect_allowed_hosts(
                        target["sourceUrl"], config
                    ),
                ): target
                for target in valid_targets
            }
            for future in as_completed(future_targets):
                target = future_targets[future]
                try:
                    fetched[target["sourceUrl"]] = future.result()
                except Exception as exc:  # Isolate one worker failure from the audit.
                    fetched[target["sourceUrl"]] = {
                        "status": None,
                        "finalUrl": target["sourceUrl"],
                        "redirectChain": [],
                        "contentType": "",
                        "body": b"",
                        "bodyTruncated": False,
                        "durationMs": None,
                        "fetchError": {
                            "type": type(exc).__name__,
                            "message": str(exc),
                        },
                    }

    results = []
    for target in targets:
        fetch = fetched.get(target["sourceUrl"], {})
        results.append(analyze_target(target, fetch, config))
    report = {
        "schemaVersion": "1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "input": input_label,
        "requestPolicy": {
            "method": "GET",
            "timeoutSeconds": config.timeout_seconds,
            "workers": config.workers,
            "maxWorkers": MAX_WORKERS,
            "maxBodyBytes": config.max_body_bytes,
            "userAgent": config.user_agent,
            "auditHeader": AUDIT_HEADER_VALUE,
            "cookies": False,
            "baseHost": host_key(urlsplit(config.base_url).hostname),
            "allowedSourceHosts": sorted(set(config.allowed_source_hosts)),
            "allowedRedirectHosts": sorted(set(config.allowed_redirect_hosts)),
            "destinationIPRule": "all resolved addresses must be globally routable",
            "sensitiveQueryRule": "credential, token, secret, signature, and provider-signed keys are rejected before GET",
        },
        "thresholds": {
            "effectivelyEmpty": {
                "rule": "contentWords < minContentWords AND contentChars < minContentChars",
                "minContentWords": config.min_content_words,
                "minContentChars": config.min_content_chars,
                "contentSelection": "main/article, else body excluding nav/header/footer/aside, else document",
            },
            "redirectHostRule": "exact hostname match after removing a leading www., plus explicit allowlist",
            "allowedRedirectHosts": sorted(set(config.allowed_redirect_hosts)),
        },
        "inventory": inventory,
        "summary": None,
        "results": results,
    }
    report["summary"] = summarize(results)
    return report


def report_exit_code(report, strict=False):
    if strict and report["summary"]["blockingFindingCount"]:
        return 1
    return 0


def positive_int(name, value, upper=None):
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{name} must be an integer") from exc
    if number < 1 or (upper is not None and number > upper):
        suffix = f" and at most {upper}" if upper is not None else ""
        raise argparse.ArgumentTypeError(f"{name} must be at least 1{suffix}")
    return number


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", "--out", type=Path, help="Write JSON here instead of stdout.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Per-request timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS:g}).",
    )
    parser.add_argument(
        "--workers",
        type=lambda value: positive_int("workers", value, MAX_WORKERS),
        default=DEFAULT_WORKERS,
    )
    parser.add_argument(
        "--max-bytes",
        type=lambda value: positive_int("max-bytes", value, MAX_BODY_BYTES),
        default=DEFAULT_MAX_BODY_BYTES,
    )
    parser.add_argument("--min-words", type=int, default=DEFAULT_MIN_CONTENT_WORDS)
    parser.add_argument("--min-chars", type=int, default=DEFAULT_MIN_CONTENT_CHARS)
    parser.add_argument(
        "--allowed-source-host",
        action="append",
        default=[],
        help="Additional public source hostname; repeat for multiple hosts.",
    )
    parser.add_argument(
        "--allowed-redirect-host",
        action="append",
        default=[],
        help="Expected redirect hostname; repeat for multiple hosts.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if any URL has a blocking finding; warnings remain non-blocking.",
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not 0 < args.timeout <= 60:
        parser.error("timeout must be greater than 0 and at most 60 seconds")
    if args.min_words < 0 or args.min_chars < 0:
        parser.error("min-words and min-chars must not be negative")
    normalized_base, base_error = normalize_article_url(args.base_url, DEFAULT_BASE_URL)
    if base_error:
        parser.error(f"invalid base-url: {base_error}")
    config = AuditConfig(
        base_url=normalized_base,
        timeout_seconds=args.timeout,
        workers=args.workers,
        max_body_bytes=args.max_bytes,
        min_content_words=args.min_words,
        min_content_chars=args.min_chars,
        allowed_source_hosts=tuple(args.allowed_source_host),
        allowed_redirect_hosts=tuple(args.allowed_redirect_host),
    )
    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"audit input error: {exc}", file=sys.stderr)
        return 2
    report = audit_data(data, config, input_label=str(args.input))
    payload = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    try:
        if args.output:
            args.output.write_text(payload, encoding="utf-8")
            summary = report["summary"]
            print(
                f"Audited {summary['auditedUrls']} URLs; "
                f"{summary['urlsWithBlockingFindings']} have blocking findings. "
                f"JSON: {args.output}",
                file=sys.stderr,
            )
        else:
            sys.stdout.write(payload)
    except OSError as exc:
        print(f"audit output error: {exc}", file=sys.stderr)
        return 2
    return report_exit_code(report, args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
