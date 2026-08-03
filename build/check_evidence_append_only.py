#!/usr/bin/env python3
"""Detect non-append-only evidence records and validation versions.

This is preventive only as a required pre-merge PR check under an external
repository ruleset. On direct pushes it is a post-receive alarm/build blocker,
not access control. Existing records, schemas, and policies may never be edited,
deleted, renamed, or copied; new versions must be monotonic.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import PurePosixPath
from typing import Any


SEMVER = re.compile(r"^[0-9]+\.[0-9]+(?:\.[0-9]+)?$")
ZERO_SHA = re.compile(r"^0+$")
EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def protected_kind(path: str) -> str | None:
    """Return the protected artifact kind, ignoring documentation files."""
    item = PurePosixPath(path)
    parts = item.parts
    if len(parts) >= 3 and parts[:2] == ("evidence", "records") and item.suffix == ".json":
        return "record"
    if (
        len(parts) == 3
        and parts[0] == "evidence"
        and parts[1] in {"policies", "schemas"}
        and item.suffix == ".json"
    ):
        return "policy" if parts[1] == "policies" else "schema"
    return None


def parse_name_status(name_status_output: str) -> list[tuple[str, tuple[str, ...]]]:
    entries: list[tuple[str, tuple[str, ...]]] = []
    for line in name_status_output.splitlines():
        if not line.strip():
            continue
        status, *paths = line.split("\t")
        entries.append((status, tuple(paths)))
    return entries


def violations(name_status_output: str) -> list[str]:
    """Return protected non-addition changes from a git name-status diff."""
    problems: list[str] = []
    for status, paths in parse_name_status(name_status_output):
        protected_paths = [path for path in paths if protected_kind(path)]
        if not protected_paths:
            continue
        # Only a plain addition is potentially allowed. Rename/copy statuses
        # include both source and destination paths and are always historical
        # rewrites when either side is protected.
        if status == "A" and len(paths) == 1:
            continue
        problems.append("\t".join((status, *paths)))
    return problems


def version_tuple(version: str) -> tuple[int, int, int]:
    parts = [int(part) for part in version.split(".")]
    return tuple((parts + [0, 0])[:3])  # type: ignore[return-value]


def version_from_path(path: str) -> str | None:
    stem = PurePosixPath(path).stem
    return stem if SEMVER.fullmatch(stem) else None


def version_addition_violations(
    name_status_output: str,
    base_paths: set[str],
    head_paths: set[str],
    added_documents: dict[str, str],
) -> list[str]:
    """Validate newly added policy/schema files against base and head trees."""
    problems: list[str] = []
    base_versions: dict[str, list[tuple[int, int, int]]] = {"policy": [], "schema": []}
    for path in base_paths:
        kind = protected_kind(path)
        version = version_from_path(path)
        if kind in base_versions and version:
            base_versions[kind].append(version_tuple(version))

    for status, paths in parse_name_status(name_status_output):
        if status != "A" or len(paths) != 1:
            continue
        path = paths[0]
        kind = protected_kind(path)
        if kind not in {"policy", "schema"}:
            continue
        version = version_from_path(path)
        if not version:
            problems.append(f"{path}: filename must be a semantic version such as 2.0.json")
            continue
        if base_versions[kind] and version_tuple(version) <= max(base_versions[kind]):
            problems.append(
                f"{path}: added {kind} version {version} must be higher than the protected base"
            )
        try:
            document: Any = json.loads(added_documents[path])
        except (KeyError, json.JSONDecodeError) as exc:
            problems.append(f"{path}: cannot read valid JSON: {exc}")
            continue
        if not isinstance(document, dict):
            problems.append(f"{path}: version artifact must contain a JSON object")
            continue
        if kind == "policy":
            if document.get("policyVersion") != version:
                problems.append(
                    f"{path}: policyVersion {document.get('policyVersion')!r} must match filename {version!r}"
                )
            schema_version = document.get("schemaVersion")
            schema_path = f"evidence/schemas/{schema_version}.json"
            if not isinstance(schema_version, str) or not SEMVER.fullmatch(schema_version):
                problems.append(f"{path}: schemaVersion must be a semantic version")
            elif schema_path not in head_paths:
                problems.append(
                    f"{path}: referenced immutable schema {schema_path} is absent from the head tree"
                )
        else:
            declared = document.get("properties", {}).get("schemaVersion", {}).get("const")
            if declared != version:
                problems.append(
                    f"{path}: schemaVersion const {declared!r} must match filename {version!r}"
                )
            if not str(document.get("$id", "")).endswith(f"/schemas/{version}.json"):
                problems.append(f"{path}: $id must end with /schemas/{version}.json")
    return problems


def run_git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args], text=True, capture_output=True, check=False
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return completed.stdout


def tree_paths(revision: str) -> set[str]:
    output = run_git(
        "ls-tree", "-r", "--name-only", revision, "--",
        "evidence/records", "evidence/policies", "evidence/schemas",
    )
    return {line for line in output.splitlines() if line}


def comparison_range(base: str, head: str, event: str) -> tuple[str, str, bool]:
    base_is_empty = bool(ZERO_SHA.fullmatch(base))
    base_revision = EMPTY_TREE_SHA if base_is_empty else base
    separator = ".." if event == "push" or base_is_empty else "..."
    return base_revision, f"{base_revision}{separator}{head}", base_is_empty


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="Protected base/before commit SHA")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument(
        "--event", choices=("pull_request", "push"), default="pull_request",
        help="PRs compare from merge-base; pushes compare the exact before/after trees.",
    )
    args = parser.parse_args(argv)

    base_revision, revision_range, base_is_empty = comparison_range(
        args.base, args.head, args.event
    )
    try:
        name_status = run_git(
            "diff", "--name-status", "--find-renames", "--find-copies-harder",
            revision_range, "--", "evidence/records", "evidence/policies", "evidence/schemas",
        )
        immutable_problems = violations(name_status)
        base_paths = set() if base_is_empty else tree_paths(base_revision)
        head_paths = tree_paths(args.head)
        added_version_paths = [
            paths[0]
            for status, paths in parse_name_status(name_status)
            if status == "A" and len(paths) == 1
            and protected_kind(paths[0]) in {"policy", "schema"}
        ]
        documents = {
            path: run_git("show", f"{args.head}:{path}") for path in added_version_paths
        }
        version_problems = version_addition_violations(
            name_status, base_paths, head_paths, documents
        )
    except RuntimeError as exc:
        print(f"append-only evidence check could not compare revisions: {exc}", file=sys.stderr)
        return 2

    problems = immutable_problems + version_problems
    if problems:
        print(
            "Evidence history and validation semantics are append-only. Add a superseding "
            "record or a new higher policy/schema version instead:",
            file=sys.stderr,
        )
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print("evidence records and validation versions are append-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
