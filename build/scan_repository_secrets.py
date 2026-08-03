#!/usr/bin/env python3
"""Fail on high-confidence credentials in the repository working tree."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from validate_evidence import CREDENTIAL_PATTERNS, secret_key_is_sensitive, value_is_empty_or_redacted


ASSIGNMENT = re.compile(
    r"(?i)[\"']?([A-Za-z][A-Za-z0-9_.-]{2,})[\"']?\s*[:=]\s*[\"']?([^\s,;\"']+)"
)
SKIP_SUFFIXES = {".zip", ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".woff", ".woff2"}
NON_SECRET_LITERAL = re.compile(r"^(?:\d+(?:\.\d+)?|true|false|none|null|read|write|\{|\[|\()$", re.I)


def scan_text(text: str, source: str) -> list[str]:
    findings: list[str] = []
    code_source = Path(source).suffix.lower() in {".py", ".js", ".mjs", ".ts", ".tsx"}
    for number, line in enumerate(text.splitlines(), start=1):
        if "secret-scan: allow" in line or "${{ secrets." in line:
            continue
        assignments = ASSIGNMENT.findall(line)
        sensitive_assignments = [
            (key, value) for key, value in assignments if secret_key_is_sensitive(key)
        ]
        unsafe_assignment = False
        for key, value in sensitive_assignments:
            quoted_literal = bool(re.search(
                rf"{re.escape(key)}[\"']?\s*[:=]\s*[\"']",
                line,
                re.IGNORECASE,
            ))
            code_reference = code_source and not quoted_literal and bool(
                re.match(r"[A-Za-z_$][A-Za-z0-9_.$]*(?:\(|$)", value)
            ) and not value.lower().startswith(("sk-", "live-", "ghp_", "akia"))
            if (
                not value_is_empty_or_redacted(value)
                and not NON_SECRET_LITERAL.fullmatch(value)
                and not code_reference
                and not any(marker in value for marker in ("getenv", "environ", "SECRET", "TOKEN"))
            ):
                findings.append(f"{source}:{number}: non-redacted value assigned to sensitive key {key!r}")
                unsafe_assignment = True
                break
        if unsafe_assignment or sensitive_assignments:
            continue
        if any(pattern.search(line) for pattern in CREDENTIAL_PATTERNS):
            findings.append(f"{source}:{number}: high-confidence credential pattern")
    return findings


def scan_file(path: Path, root: Path) -> list[str]:
    relative = path.relative_to(root).as_posix()
    if path.suffix.lower() in SKIP_SUFFIXES:
        return []
    try:
        data = path.read_bytes()
    except OSError as exc:
        return [f"{relative}: cannot read for secret scan: {exc}"]
    if b"\x00" in data or len(data) > 5 * 1024 * 1024:
        return []
    return scan_text(data.decode("utf-8", errors="ignore"), relative)


def repository_paths(root: Path) -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root, text=True, capture_output=True, check=False,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return [root / line for line in completed.stdout.splitlines() if line]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        findings = [finding for path in repository_paths(root) for finding in scan_file(path, root)]
    except RuntimeError as exc:
        print(f"repository secret scan failed to enumerate files: {exc}", file=sys.stderr)
        return 2
    if findings:
        print("repository secret scan found possible credentials:", file=sys.stderr)
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        return 1
    print("repository secret scan: no high-confidence credentials found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
