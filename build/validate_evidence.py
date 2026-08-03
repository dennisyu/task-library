#!/usr/bin/env python3
"""Validate append-only E1-E4 task trial records and build a dashboard overlay.

The validator intentionally uses only the Python standard library so it can run
in the repository's existing GitHub Actions job. JSON Schema checks are followed
by semantic checks that JSON Schema cannot express: references, acceptance
math, arm comparability, evidence qualification, skill drift, and staleness.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import hmac
import json
import math
import os
import re
import sys
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from itertools import product
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote_to_bytes, urlparse


ROOT = Path(__file__).resolve().parent.parent
LEVELS = ("E0", "E1", "E2", "E3", "E4")
AI_MODES = {"ai-only", "human-ai"}
VERIFIED_ARTIFACT_STATUSES = {"verified-local", "verified-inline"}
MUTABLE_VERSION = re.compile(r"^(latest|current|default|auto|head|main|master)$", re.I)
SEMVER = re.compile(r"^[0-9]+\.[0-9]+(?:\.[0-9]+)?$")
SHA256_REF = re.compile(r"^sha256:[a-f0-9]{64}$")
ISSUER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
TRUST_MAP_FIELDS = (
    "trustedReceiptIssuers",
    "trustedEvaluatorIssuers",
    "trustedProductionDataIssuers",
    "trustedOutcomeIssuers",
)
RSA_KEY_FIELDS = {"algorithm", "modulusHex", "exponent"}
RSA_PUBLIC_EXPONENT = 65537
MIN_RSA_MODULUS_BITS = 2048
MAX_RSA_MODULUS_BITS = 8192
SENSITIVE_QUERY_KEYS = {
    "access_token", "accesstoken", "api_key", "apikey", "auth", "authorization",
    "credential", "key", "password", "secret", "sig", "signature", "token",
    "x-amz-credential", "x-amz-signature", "x-goog-signature",
}
FORBIDDEN_SECRET_KEYS = {
    "api_key", "apikey", "password", "passwd", "pwd", "token", "access_token",
    "refresh_token", "secret", "client_secret", "private_key", "authorization",
    "credential", "credentials",
}
REDACTED_PLACEHOLDERS = {
    "", "***", "<redacted>", "[redacted]", "redacted", "removed", "not-stored"
}
CREDENTIAL_PATTERNS = (
    re.compile(
        r"(?i)\b(?:password|passwd|pwd|api[_-]?key|access[_-]?token|refresh[_-]?token|"
        r"client[_-]?secret|secret|authorization)\s*[:=]\s*[^\s,;]{4,}"
    ),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{16,}={0,2}\b"),
)
PII_PATTERNS = (
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}\b"),
)
TEXT_KEY_ASSIGNMENT = re.compile(
    r"(?i)[\"']?([A-Za-z][A-Za-z0-9_.-]{2,})[\"']?\s*[:=]\s*[\"']?([^\s,;\"']+)"
)
SUPPORTED_SCHEMA_KEYWORDS = {
    "$schema", "$id", "$ref", "$defs", "title", "description", "type", "const",
    "enum", "oneOf", "properties", "required", "additionalProperties", "items",
    "minItems", "uniqueItems", "minLength", "pattern", "format", "minimum",
    "maximum", "exclusiveMinimum",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_timestamp(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("timezone offset is required")
    return parsed.astimezone(timezone.utc)


def parse_as_of(value: str | None) -> datetime:
    if not value:
        return utc_now()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return datetime.fromisoformat(value + "T23:59:59+00:00")
    return parse_timestamp(value)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def preregistration_receipt_payload(
    record: dict[str, Any], preregistration: dict[str, Any]
) -> dict[str, Any]:
    """Return the authority-signed publication envelope for a planned trial.

    The protocol digest already binds the complete planned design.  The
    explicit subject identity prevents an otherwise byte-identical protocol
    receipt from being transplanted to a different record, trial, task, or
    protocol identity.
    """
    binding = preregistration["binding"]
    protocol = record["trial"]["protocol"]
    task = record["task"]
    return {
        "issuerId": binding.get("issuerId"),
        "subject": {
            "recordId": record["recordId"],
            "trialId": record["trial"]["trialId"],
            "protocolId": protocol["protocolId"],
            "protocolVersion": protocol["version"],
            "taskSlug": task["slug"],
            "taskContractVersion": task["taskContractVersion"],
            "skillSha256": task["skill"]["sha256"],
        },
        "protocolArtifactId": preregistration["protocolArtifactId"],
        "protocolSha256": preregistration["protocolSha256"],
        "publishedAt": preregistration["publishedAt"],
    }


def rsa_public_key_errors(modulus_hex: Any, exponent: Any) -> list[str]:
    """Validate the deliberately narrow RSA trust-key profile used by policy.

    Trust anchors are configuration, not ordinary evidence input.  Rejecting
    malformed or weak parameters before signature verification prevents an
    accidentally provisioned key (for example exponent 1) from turning a
    PKCS#1 encoded digest into a signature that needs no private key.
    """
    errors: list[str] = []
    if not isinstance(exponent, int) or isinstance(exponent, bool):
        errors.append("exponent must be an integer")
    elif exponent != RSA_PUBLIC_EXPONENT:
        errors.append(f"exponent must be {RSA_PUBLIC_EXPONENT}")
    if not isinstance(modulus_hex, str) or not re.fullmatch(r"[0-9a-fA-F]+", modulus_hex):
        errors.append("modulusHex must contain only hexadecimal digits")
        return errors
    if len(modulus_hex) > 1 and modulus_hex.startswith("0"):
        errors.append("modulusHex must use canonical hexadecimal without a leading zero")
    try:
        modulus = int(modulus_hex, 16)
    except (TypeError, ValueError):
        errors.append("modulusHex is not a valid integer")
        return errors
    bit_length = modulus.bit_length()
    if bit_length < MIN_RSA_MODULUS_BITS:
        errors.append(f"modulus must be at least {MIN_RSA_MODULUS_BITS} bits")
    if bit_length > MAX_RSA_MODULUS_BITS:
        errors.append(f"modulus must be at most {MAX_RSA_MODULUS_BITS} bits")
    if modulus % 2 == 0:
        errors.append("modulus must be odd")
    if isinstance(exponent, int) and not isinstance(exponent, bool):
        if math.gcd(modulus, exponent) != 1:
            errors.append("modulus must be coprime to the public exponent")
    return errors


def policy_trust_key_errors(policy: Any) -> list[str]:
    """Validate every configured trust map and its public-key metadata."""
    if not isinstance(policy, dict):
        return ["policy must be a JSON object"]
    errors: list[str] = []
    for field in TRUST_MAP_FIELDS:
        issuers = policy.get(field)
        if not isinstance(issuers, dict):
            errors.append(f"{field} must be an object")
            continue
        for issuer_id, metadata in issuers.items():
            where = f"{field}.{issuer_id}"
            if not isinstance(issuer_id, str) or not ISSUER_ID.fullmatch(issuer_id):
                errors.append(f"{where}: issuer ID has an invalid shape")
            if not isinstance(metadata, dict):
                errors.append(f"{where}: trust-key metadata must be an object")
                continue
            missing = RSA_KEY_FIELDS - set(metadata)
            extra = set(metadata) - RSA_KEY_FIELDS
            if missing:
                errors.append(f"{where}: missing fields {sorted(missing)}")
            if extra:
                errors.append(f"{where}: unexpected fields {sorted(extra)}")
            if metadata.get("algorithm") != "rsa-pkcs1v15-sha256":
                errors.append(f"{where}: unsupported signature algorithm")
            errors.extend(
                f"{where}: {message}"
                for message in rsa_public_key_errors(
                    metadata.get("modulusHex"), metadata.get("exponent")
                )
            )
    return errors


def verify_rsa_pkcs1v15_sha256(
    payload: bytes, signature_b64: str, modulus_hex: str, exponent: int
) -> bool:
    if rsa_public_key_errors(modulus_hex, exponent):
        return False
    if not isinstance(payload, bytes) or not isinstance(signature_b64, str):
        return False
    try:
        modulus = int(modulus_hex, 16)
        signature = base64.b64decode(signature_b64, validate=True)
        width = (modulus.bit_length() + 7) // 8
        if len(signature) != width:
            return False
        signature_integer = int.from_bytes(signature, "big")
        if signature_integer >= modulus:
            return False
        encoded = pow(signature_integer, exponent, modulus).to_bytes(width, "big")
    except (TypeError, ValueError, binascii.Error, OverflowError):
        return False
    digest_info = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(payload).digest()
    padding_length = width - len(digest_info) - 3
    if padding_length < 8:
        return False
    expected = b"\x00\x01" + b"\xff" * padding_length + b"\x00" + digest_info
    return hmac.compare_digest(encoded, expected)


def protocol_binding_payload(record: dict[str, Any]) -> dict[str, Any]:
    """Return the planned trial fields an external preregistration must bind.

    Outcomes and attempt data are deliberately excluded.  The design, exact
    input fingerprints, planned arms/stacks, rubric, evaluator, and primary E3
    comparison are included so cases or arms cannot be dropped post hoc while
    retaining a valid preregistration receipt.
    """
    trial = record["trial"]
    protocol = trial["protocol"]
    artifact_by_id = {
        artifact["artifactId"]: artifact for artifact in record.get("artifacts", [])
    }
    protocol_fields = {
        key: protocol[key]
        for key in (
            "protocolId", "version", "assignment", "minimumWeightedScore",
            "acceptanceCriteria", "criticalFailures", "evaluator",
        )
    }
    if "primaryComparison" in protocol:
        protocol_fields["primaryComparison"] = protocol["primaryComparison"]
    cases = []
    for case in sorted(trial["cases"], key=lambda item: item["caseId"]):
        cases.append({
            **{key: value for key, value in case.items() if key != "inputArtifactIds"},
            "inputArtifacts": [
                {
                    "artifactId": artifact_id,
                    "sha256": artifact_by_id.get(artifact_id, {}).get("sha256"),
                }
                for artifact_id in sorted(case["inputArtifactIds"])
            ],
        })
    planned_arms = sorted(
        (
            {
                "armId": arm["armId"],
                "mode": arm["mode"],
                "stackId": arm.get("stackId"),
                "operatorIds": arm["operatorIds"],
            }
            for arm in record["arms"]
        ),
        key=lambda item: item["armId"],
    )
    planned_stacks = sorted(record["testedStacks"], key=lambda item: item["stackId"])
    payload = {
        "recordIdentity": {
            "schemaVersion": record["schemaVersion"],
            "recordId": record["recordId"],
            "policyVersion": record["claim"]["policyVersion"],
            "claimedEvidenceLevel": record["claim"]["evidenceLevel"],
        },
        "task": record["task"],
        "protocol": protocol_fields,
        "trialDesign": {
            "trialId": trial["trialId"],
            "startedAt": trial["startedAt"],
            "completedAt": trial["completedAt"],
            "environment": trial["environment"],
            "caseDesign": trial["caseDesign"],
            "cases": cases,
        },
        "plannedArms": planned_arms,
        "plannedStacks": planned_stacks,
        "plannedContextArtifacts": [
            {"artifactId": artifact_id, "sha256": artifact_by_id.get(artifact_id, {}).get("sha256")}
            for artifact_id in sorted({
                artifact_id
                for stack in record["testedStacks"]
                for artifact_id in (
                    list(stack["contextArtifactIds"])
                    + ([stack["memory"]["snapshotArtifactId"]]
                       if stack["memory"].get("snapshotArtifactId") else [])
                    + [
                        release["artifactId"]
                        for component in [stack["model"], stack["orchestrator"], *stack["tools"]]
                        for release in [component.get("immutableRelease") or {}]
                        if release.get("artifactId")
                    ]
                )
            })
        ],
    }
    if record.get("production"):
        production = record["production"]
        payload["productionPlan"] = {
            key: production[key]
            for key in (
                "periodStart", "periodEnd", "deploymentId", "accountableOwnerId",
                "samplingFrameArtifactId", "eventLedgerArtifactId", "eventLedgerIssuerId",
            )
        }
        payload["productionPlan"]["outcomeDefinitions"] = [
            {
                key: outcome[key]
                for key in (
                    "metric", "unit", "baseline", "direction", "target",
                    "armId", "stackId", "attemptIds", "periodStart", "periodEnd",
                    "outcomeIssuerId",
                )
            }
            for outcome in production["downstreamOutcomes"]
        ]
    return payload


def protocol_binding_digest(record: dict[str, Any]) -> str:
    return canonical_sha256(protocol_binding_payload(record))


def case_input_digests(record: dict[str, Any], case_id: str) -> list[str]:
    artifact_by_id = {item["artifactId"]: item for item in record["artifacts"]}
    case = next(item for item in record["trial"]["cases"] if item["caseId"] == case_id)
    return sorted(
        artifact_by_id[artifact_id]["sha256"]
        for artifact_id in case["inputArtifactIds"]
        if artifact_id in artifact_by_id
    )


def criterion_receipt_payload(
    record: dict[str, Any], arm_id: str, attempt: dict[str, Any], criterion: dict[str, Any]
) -> dict[str, Any]:
    """Return the evaluator-signed, immutable result envelope for one criterion.

    Signatures are excluded to avoid a circular payload, but every other
    attempt/acceptance field and every result-affecting binding is included.
    A receipt therefore cannot be replayed into another record/trial or survive
    post-signature changes to scoring, cost, labor, recovery, errors, timing,
    outputs, protocol, task/skill, arm, or stack.
    """
    designated_receipt_ids = {
        item.get("receiptArtifactId")
        for arm in record["arms"]
        for candidate_attempt in arm["attempts"]
        for item in candidate_attempt["acceptance"]["criterionResults"]
        if item.get("receiptArtifactId")
    }
    criterion_result_object_ids = {
        id(item)
        for arm in record["arms"]
        for candidate_attempt in arm["attempts"]
        for item in candidate_attempt["acceptance"]["criterionResults"]
    }
    artifact_object_ids = {id(item) for item in record["artifacts"]}
    designated_receipt_artifact_object_ids = {
        id(item)
        for item in record["artifacts"]
        if item.get("artifactId") in designated_receipt_ids
    }

    def result_binding_copy(value: Any) -> Any:
        """Copy the record while breaking only evaluator-receipt cycles.

        Receipt signatures cannot sign themselves.  Likewise, the artifact
        containing a canonical receipt cannot include its own URI or digest in
        those same canonical bytes.  All other fields -- including auxiliary
        evidence artifact bytes/digests and other signature types -- remain in
        the signed envelope.
        """
        if isinstance(value, list):
            return [result_binding_copy(item) for item in value]
        if not isinstance(value, dict):
            return value
        if id(value) in criterion_result_object_ids:
            return {
                **{
                    key: result_binding_copy(child)
                    for key, child in value.items()
                    if key != "receiptSignature"
                },
                "signatureBinding": "verified-separately-to-break-self-reference",
            }
        if id(value) in designated_receipt_artifact_object_ids:
            return {
                **{
                    key: result_binding_copy(child)
                    for key, child in value.items()
                    if key not in {"uri", "sha256"}
                },
                "contentBinding": "canonical-evaluator-receipt-self-reference",
            }
        if id(value) in artifact_object_ids:
            return {
                **{
                    key: result_binding_copy(child)
                    for key, child in value.items()
                    if key != "uri"
                },
                # Binding the URI's digest preserves exact URI identity without
                # recursively embedding large inline data URIs in every receipt.
                "uriSha256": hashlib.sha256(value["uri"].encode("utf-8")).hexdigest(),
            }
        return {key: result_binding_copy(child) for key, child in value.items()}

    result_binding = result_binding_copy(record)
    return {
        "receiptType": "criterion-evaluation-v1",
        "signedCriterion": {
            "armId": arm_id,
            "attemptId": attempt["attemptId"],
            "criterionId": criterion["criterionId"],
            "receiptArtifactId": criterion.get("receiptArtifactId"),
            "receiptIssuerId": criterion.get("receiptIssuerId"),
        },
        "recordBindingSha256": canonical_sha256(result_binding),
    }


def sampling_frame_payload(record: dict[str, Any]) -> dict[str, Any]:
    production = record["production"]
    return {
        "deploymentId": production["deploymentId"],
        "periodStart": production["periodStart"],
        "periodEnd": production["periodEnd"],
        "cases": [
            {"caseId": case["caseId"], "inputDigests": case_input_digests(record, case["caseId"])}
            for case in sorted(record["trial"]["cases"], key=lambda item: item["caseId"])
        ],
        "arms": [
            {"armId": arm["armId"], "mode": arm["mode"], "stackId": arm.get("stackId")}
            for arm in sorted(record["arms"], key=lambda item: item["armId"])
        ],
    }


def production_event_ledger_payload(record: dict[str, Any]) -> dict[str, Any]:
    artifact_by_id = {item["artifactId"]: item for item in record["artifacts"]}
    return {
        "deploymentId": record["production"]["deploymentId"],
        "issuerId": record["production"]["eventLedgerIssuerId"],
        "protocolDigest": protocol_binding_digest(record),
        "events": [
            {
                "armId": arm["armId"],
                "stackId": arm.get("stackId"),
                "attemptId": attempt["attemptId"],
                "caseId": attempt["caseId"],
                "startedAt": attempt["startedAt"],
                "completedAt": attempt["completedAt"],
                "status": attempt["status"],
                "inputDigests": case_input_digests(record, attempt["caseId"]),
                "outputDigests": sorted(
                    artifact_by_id[artifact_id]["sha256"]
                    for artifact_id in attempt["outputArtifactIds"]
                    if artifact_id in artifact_by_id
                ),
                "errorIds": sorted(error["errorId"] for error in attempt["errors"]),
            }
            for arm in sorted(record["arms"], key=lambda item: item["armId"])
            for attempt in sorted(arm["attempts"], key=lambda item: item["attemptId"])
        ],
        "incidents": sorted(
            record["production"]["incidents"], key=lambda item: item["incidentId"]
        ),
    }


def downstream_outcome_payload(record: dict[str, Any], outcome: dict[str, Any]) -> dict[str, Any]:
    production = record["production"]
    payload = {
        key: outcome[key]
        for key in (
            "metric", "unit", "value", "baseline", "direction", "target",
            "armId", "stackId", "attemptIds", "periodStart", "periodEnd",
            "outcomeIssuerId",
        )
    } | {
        "deploymentId": production["deploymentId"],
        "accountableOwnerId": production["accountableOwnerId"],
        "protocolDigest": protocol_binding_digest(record),
        "guardrailIncidents": sorted(
            (
                incident for incident in production["incidents"]
                if incident["armId"] == outcome["armId"]
                and incident["stackId"] == outcome["stackId"]
                and set(incident["attemptIds"]).issubset(set(outcome["attemptIds"]))
            ),
            key=lambda item: item["incidentId"],
        ),
    }
    if "window" in outcome:
        payload["window"] = outcome["window"]
    return payload


def secret_key_is_sensitive(key: Any) -> bool:
    raw = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(key))
    normalized = re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_")
    tokens = [token for token in normalized.split("_") if token]
    if normalized in FORBIDDEN_SECRET_KEYS:
        return True
    if any(token in {"password", "passwd", "pwd", "token", "secret", "credential"}
           for token in tokens):
        return True
    return bool(
        len(tokens) >= 2 and tokens[-2:] in (["api", "key"], ["private", "key"])
    )


def value_is_empty_or_redacted(value: Any) -> bool:
    if value in (None, "", [], {}):
        return True
    return isinstance(value, str) and value.strip().lower() in REDACTED_PLACEHOLDERS


def text_contains_secret(text: str) -> bool:
    if any(pattern.search(text) for pattern in CREDENTIAL_PATTERNS):
        return True
    return any(
        secret_key_is_sensitive(key) and not value_is_empty_or_redacted(value)
        for key, value in TEXT_KEY_ASSIGNMENT.findall(text)
    )


def secret_scan_errors(value: Any, path: str = "$") -> list[str]:
    """Reject credential-bearing keys and high-confidence secrets anywhere."""
    errors: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if secret_key_is_sensitive(key) and not value_is_empty_or_redacted(child):
                errors.append(f"{child_path}: forbidden credential-bearing field")
            errors.extend(secret_scan_errors(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(secret_scan_errors(child, f"{path}[{index}]"))
    elif isinstance(value, str):
        if text_contains_secret(value):
            errors.append(f"{path}: contains a high-confidence credential pattern")
    return errors


def component_release_is_immutable(
    component: dict[str, Any],
    artifacts: dict[str, dict[str, Any]],
    artifact_statuses: dict[str, str],
) -> bool:
    release = component.get("immutableRelease")
    if not isinstance(release, dict):
        return False
    identifier = release.get("identifier", "")
    artifact_id = release.get("artifactId")
    if release.get("kind") == "artifact-digest":
        if not SHA256_REF.fullmatch(identifier) or not artifact_id:
            return False
        artifact = artifacts.get(artifact_id)
        return bool(
            artifact
            and artifact_statuses.get(artifact_id) in VERIFIED_ARTIFACT_STATUSES
            and identifier == f"sha256:{artifact['sha256']}"
        )
    if release.get("kind") == "provider-snapshot":
        # Identifier shape is not provider attestation. A future policy can
        # enable this only with a trusted resolver or signed provider receipt.
        return False
    return False


def stack_release_is_immutable(
    stack: dict[str, Any],
    artifacts: dict[str, dict[str, Any]],
    artifact_statuses: dict[str, str],
) -> bool:
    return (
        component_release_is_immutable(stack["model"], artifacts, artifact_statuses)
        and component_release_is_immutable(stack["orchestrator"], artifacts, artifact_statuses)
        and all(
            component_release_is_immutable(tool, artifacts, artifact_statuses)
            for tool in stack["tools"]
        )
    )


def load_artifact_bytes(artifact: dict[str, Any], repo_root: Path) -> tuple[bytes | None, str]:
    parsed = urlparse(artifact["uri"])
    if not parsed.scheme:
        artifact_path = (repo_root / artifact["uri"]).resolve()
        try:
            artifact_path.relative_to(repo_root.resolve())
        except ValueError:
            return None, "claimed-only"
        try:
            content = artifact_path.read_bytes()
        except OSError:
            return None, "claimed-only"
        return content, "verified-local"
    if parsed.scheme == "data":
        try:
            header, payload = artifact["uri"].split(",", 1)
            content = (
                base64.b64decode(payload, validate=True)
                if ";base64" in header.lower()
                else unquote_to_bytes(payload)
            )
        except (ValueError, binascii.Error):
            return None, "claimed-only"
        if len(content) <= 1024 * 1024:
            return content, "verified-inline"
    return None, "claimed-only"


def artifact_verification_status(artifact: dict[str, Any], repo_root: Path) -> str:
    """Classify whether the validator obtained bytes and recomputed their digest.

    Remote URLs are never fetched: doing so would leak access patterns and can
    accidentally dereference private or credentialed links.  A plain remote URL
    therefore remains `claimed-only` even when a SHA-256 field accompanies it.
    """
    content, status = load_artifact_bytes(artifact, repo_root)
    if (
        content is not None
        and hashlib.sha256(content).hexdigest() == artifact["sha256"]
        and artifact["access"] == "public"
        and not artifact["containsSensitiveData"]
        and artifact["redaction"] in {"none-needed", "redacted"}
    ):
        return status
    if content is not None and hashlib.sha256(content).hexdigest() == artifact["sha256"]:
        return "privacy-blocked"
    return "claimed-only"


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def round_or_none(value: float | None, digits: int = 4) -> float | None:
    return round(value, digits) if value is not None else None


def unique(values: list[Any]) -> bool:
    markers = [json.dumps(value, sort_keys=True, separators=(",", ":")) for value in values]
    return len(markers) == len(set(markers))


def json_type_matches(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, False)


def unsupported_schema_keywords(schema: Any, path: str = "$", *, property_map: bool = False) -> list[str]:
    errors: list[str] = []
    if isinstance(schema, dict):
        for key, child in schema.items():
            if not property_map and key not in SUPPORTED_SCHEMA_KEYWORDS:
                errors.append(f"{path}: unsupported JSON Schema keyword {key!r}")
            child_is_property_map = key in {"properties", "$defs"}
            if child_is_property_map and isinstance(child, dict):
                for name, subschema in child.items():
                    errors.extend(unsupported_schema_keywords(subschema, f"{path}.{key}.{name}"))
            elif key not in {"required", "enum"}:
                errors.extend(unsupported_schema_keywords(child, f"{path}.{key}"))
    elif isinstance(schema, list):
        for index, child in enumerate(schema):
            if isinstance(child, (dict, list)):
                errors.extend(unsupported_schema_keywords(child, f"{path}[{index}]"))
    return errors


def resolve_ref(root_schema: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise ValueError(f"only local schema refs are supported: {ref}")
    node: Any = root_schema
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        node = node[part]
    return node


def schema_errors(
    value: Any,
    schema: dict[str, Any],
    root_schema: dict[str, Any],
    path: str = "$",
) -> list[str]:
    """Validate the JSON-Schema subset used by versioned evidence schemas."""
    if "$ref" in schema:
        return schema_errors(value, resolve_ref(root_schema, schema["$ref"]), root_schema, path)
    if "oneOf" in schema:
        candidates = [schema_errors(value, part, root_schema, path) for part in schema["oneOf"]]
        if sum(not errs for errs in candidates) != 1:
            return [f"{path}: must match exactly one allowed shape"]
        return []

    errors: list[str] = []
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: must equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} is not one of {schema['enum']}")

    expected = schema.get("type")
    if expected:
        options = expected if isinstance(expected, list) else [expected]
        if not any(json_type_matches(value, option) for option in options):
            return [f"{path}: expected {' or '.join(options)}, got {type(value).__name__}"]

    if isinstance(value, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                errors.append(f"{path}: missing required property {key!r}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{path}: unexpected property {key!r}")
        for key, child in properties.items():
            if key in value:
                errors.extend(schema_errors(value[key], child, root_schema, f"{path}.{key}"))

    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: needs at least {schema['minItems']} item(s)")
        if schema.get("uniqueItems") and not unique(value):
            errors.append(f"{path}: items must be unique")
        if "items" in schema:
            for index, item in enumerate(value):
                errors.extend(schema_errors(item, schema["items"], root_schema, f"{path}[{index}]"))

    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{path}: must contain at least {schema['minLength']} character(s)")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: does not match required pattern")
        fmt = schema.get("format")
        try:
            if fmt == "uuid":
                uuid.UUID(value)
            elif fmt == "date-time":
                parse_timestamp(value)
            elif fmt == "date":
                date.fromisoformat(value)
        except (ValueError, TypeError):
            errors.append(f"{path}: invalid {fmt}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value):
            errors.append(f"{path}: number must be finite")
            return errors
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: must be >= {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: must be <= {schema['maximum']}")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            errors.append(f"{path}: must be > {schema['exclusiveMinimum']}")
    return errors


class SemanticResult:
    def __init__(self, source: Path, record: dict[str, Any]):
        self.source = source
        self.record = record
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.stale_reasons: list[str] = []
        self.qualified_levels: list[str] = []
        self.arm_metrics: list[dict[str, Any]] = []
        self.qualifying_ai_arm_ids: dict[str, list[str]] = {}
        self.selected_ai_arm_ids: list[str] = []
        self.selected_public_arm_ids: list[str] = []
        self.public_arm_metrics: list[dict[str, Any]] = []
        self.artifact_verification: list[dict[str, str]] = []
        self.derived_interpretation: str | None = None
        self.schema_version: str | None = record.get("schemaVersion")
        self.policy_version: str | None = record.get("claim", {}).get("policyVersion")
        self.expires_at: datetime | None = None

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warning(self, message: str) -> None:
        self.warnings.append(message)

    def stale(self, message: str) -> None:
        self.stale_reasons.append(message)

    @property
    def qualified_level(self) -> str:
        return max(self.qualified_levels, key=LEVELS.index) if self.qualified_levels else "E0"


class ValidationCatalog:
    """Resolve the exact immutable schema and policy named by each record."""

    def __init__(self, schema_dir: Path, policy_dir: Path):
        self.schema_dir = schema_dir
        self.policy_dir = policy_dir
        self._schemas: dict[str, dict[str, Any]] = {}
        self._policies: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _load_version(directory: Path, version: str, label: str) -> dict[str, Any]:
        if not SEMVER.fullmatch(version):
            raise ValueError(f"invalid {label} version {version!r}")
        path = directory / f"{version}.json"
        if not path.exists():
            raise ValueError(f"unknown {label} version {version!r} ({path})")
        return json.loads(path.read_text(encoding="utf-8"))

    def schema(self, version: str) -> dict[str, Any]:
        if version not in self._schemas:
            schema = self._load_version(self.schema_dir, version, "schema")
            unsupported = unsupported_schema_keywords(schema)
            if unsupported:
                raise ValueError("; ".join(unsupported))
            declared = schema.get("properties", {}).get("schemaVersion", {}).get("const")
            if declared != version:
                raise ValueError(
                    f"schema file {version}.json declares schemaVersion {declared!r}"
                )
            if not str(schema.get("$id", "")).endswith(f"/schemas/{version}.json"):
                raise ValueError(
                    f"schema file {version}.json has a non-versioned or mismatched $id"
                )
            self._schemas[version] = schema
        return self._schemas[version]

    def policy(self, version: str) -> dict[str, Any]:
        if version not in self._policies:
            policy = self._load_version(self.policy_dir, version, "policy")
            if policy.get("policyVersion") != version:
                raise ValueError(
                    f"policy file {version}.json declares policyVersion {policy.get('policyVersion')!r}"
                )
            trust_errors = policy_trust_key_errors(policy)
            if trust_errors:
                raise ValueError("; ".join(trust_errors))
            self._policies[version] = policy
        return self._policies[version]

    def bundle_for(self, record: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        schema_version = record.get("schemaVersion")
        policy_version = record.get("claim", {}).get("policyVersion")
        if not isinstance(schema_version, str) or not isinstance(policy_version, str):
            raise ValueError("record must declare schemaVersion and claim.policyVersion")
        schema = self.schema(schema_version)
        policy = self.policy(policy_version)
        if policy.get("schemaVersion") != schema_version:
            raise ValueError(
                f"policy {policy_version} requires schema {policy.get('schemaVersion')}, "
                f"not record schema {schema_version}"
            )
        if record.get("$schema") and record["$schema"] != schema.get("$id"):
            raise ValueError(
                f"record $schema {record['$schema']!r} does not match immutable schema ID "
                f"{schema.get('$id')!r}"
            )
        return schema, policy

    def versions(self, directory: Path) -> list[str]:
        return sorted(
            (path.stem for path in directory.glob("*.json") if SEMVER.fullmatch(path.stem)),
            key=lambda value: tuple(int(part) for part in value.split(".")),
        )

    @property
    def schema_versions(self) -> list[str]:
        return self.versions(self.schema_dir)

    @property
    def policy_versions(self) -> list[str]:
        return self.versions(self.policy_dir)

    def validate_catalog(self) -> None:
        for version in self.schema_versions:
            self.schema(version)
        for version in self.policy_versions:
            policy = self.policy(version)
            self.schema(policy.get("schemaVersion", ""))


def load_task_catalog(path: Path, repo_root: Path) -> dict[str, dict[str, Any]]:
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            task["slug"]: task
            for category in data.get("categories", [])
            for task in category.get("tasks", [])
            if task.get("slug")
        }
    registry_path = repo_root / "build" / "registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8")).get("skills", {})
    return {slug: entry for slug, entry in registry.items()}


def check_references(
    result: SemanticResult,
    values: list[str],
    known: set[str],
    location: str,
) -> None:
    for value in values:
        if value not in known:
            result.error(f"{location} references unknown artifact {value!r}")


def check_artifact_kinds(
    result: SemanticResult,
    values: list[str],
    artifacts: dict[str, dict[str, Any]],
    allowed: set[str],
    location: str,
) -> None:
    for value in values:
        artifact = artifacts.get(value)
        if artifact and artifact["kind"] not in allowed:
            result.error(
                f"{location} references {artifact['kind']!r} artifact {value!r}; expected {sorted(allowed)}"
            )


def measurements_complete(attempts: list[dict[str, Any]], required: list[str]) -> bool:
    return bool(attempts) and all(
        all(key in (attempt.get("measurements") or {}) for key in required)
        for attempt in attempts
    )


def arm_summary(arm: dict[str, Any]) -> dict[str, Any]:
    attempts = arm["attempts"]
    completed = [attempt for attempt in attempts if attempt["status"] == "completed"]
    evaluated = [
        attempt for attempt in attempts
        if attempt["status"] == "completed" and attempt["acceptance"]["overall"] != "not-evaluated"
    ]
    accepted = [attempt for attempt in evaluated if attempt["acceptance"]["overall"] == "accepted"]
    measurements = [attempt.get("measurements") or {} for attempt in evaluated]
    quality = mean([item["quality"] for item in measurements if "quality" in item])
    scope = mean([item["endToEndScope"] for item in measurements if "endToEndScope" in item])
    generalization = mean([item["generalization"] for item in measurements if "generalization" in item])
    autonomy = mean([item["autonomousShare"] for item in measurements if "autonomousShare" in item])
    # Aborted and selectively unevaluated runs are unsuccessful outcomes for
    # reliability. Keeping them in the denominator prevents cherry-picking.
    reliability = len(accepted) / len(attempts) if attempts else None
    components = [quality, reliability, autonomy, scope, generalization]
    tci = None
    if arm["mode"] in AI_MODES and all(value is not None for value in components):
        product = math.prod(float(value) for value in components)
        tci = 100 * product ** (1 / 5)

    total_supervision = sum(
        attempt["labor"]["supervisionMinutes"] + attempt["labor"]["reviewMinutes"]
        for attempt in attempts
    )
    total_recovery = sum(
        error["recovery"]["minutes"]
        for attempt in attempts
        for error in attempt["errors"]
    )
    total_supervision += total_recovery
    total_preparation = sum(attempt["labor"]["preparationMinutes"] for attempt in attempts)
    total_human_touch = sum(
        attempt["labor"]["preparationMinutes"]
        + attempt["labor"]["operatorMinutes"]
        + attempt["labor"]["supervisionMinutes"]
        + attempt["labor"]["reviewMinutes"]
        for attempt in attempts
    ) + total_recovery
    elapsed_minutes = [
        (parse_timestamp(attempt["completedAt"]) - parse_timestamp(attempt["startedAt"])).total_seconds() / 60
        for attempt in attempts
    ]
    errors = [error for attempt in attempts for error in attempt["errors"]]
    severities = Counter(error["severity"] for error in errors)
    recovered = sum(error["recovery"]["successful"] is True for error in errors)
    cost_values = [attempt["cost"]["amount"] for attempt in attempts if "cost" in attempt]
    return {
        "armId": arm["armId"],
        "mode": arm["mode"],
        "stackId": arm.get("stackId"),
        "attempts": len(attempts),
        "completedAttempts": len(completed),
        "abortedAttempts": sum(attempt["status"] == "aborted" for attempt in attempts),
        "notEvaluatedAttempts": sum(
            attempt["acceptance"]["overall"] == "not-evaluated" for attempt in attempts
        ),
        "evaluatedAttempts": len(evaluated),
        "acceptedAttempts": len(accepted),
        "acceptanceRate": round_or_none(reliability),
        "evaluationRate": round_or_none(len(evaluated) / len(attempts) if attempts else None),
        "quality": round_or_none(quality),
        "autonomousShare": round_or_none(autonomy),
        "endToEndScope": round_or_none(scope),
        "generalization": round_or_none(generalization),
        "taskCapabilityIndex": round_or_none(tci, 2),
        "meanElapsedMinutes": round_or_none(mean(elapsed_minutes), 2),
        "preparationMinutes": round(total_preparation, 2),
        "supervisionMinutes": round(total_supervision, 2),
        "supervisionMinutesPerAcceptedOutcome": (
            round(total_supervision / len(accepted), 2) if accepted else None
        ),
        "humanTouchMinutes": round(total_human_touch, 2),
        "recoveryMinutes": round(total_recovery, 2),
        "costUsd": round(sum(cost_values), 4) if cost_values else None,
        "errorsBySeverity": dict(sorted(severities.items())),
        "recoveredErrors": recovered,
    }


def derive_interpretation(
    metrics: list[dict[str, Any]], minimum_acceptance_rate: float
) -> str | None:
    rates = [
        metric["acceptanceRate"]
        for metric in metrics
        if metric["mode"] in AI_MODES and metric["acceptanceRate"] is not None
    ]
    if not rates:
        return None
    supported = [rate >= minimum_acceptance_rate for rate in rates]
    if all(supported):
        return "supports-capability"
    if not any(supported):
        return "does-not-support-capability"
    return "mixed"


def validate_semantics(
    source: Path,
    record: dict[str, Any],
    policy: dict[str, Any],
    task_catalog: dict[str, dict[str, Any]],
    repo_root: Path,
    as_of: datetime,
) -> SemanticResult:
    result = SemanticResult(source, record)
    result.errors.extend(secret_scan_errors(record))
    result.errors.extend(
        f"policy trust configuration: {message}"
        for message in policy_trust_key_errors(policy)
    )
    claim = record["claim"]
    trial = record["trial"]
    protocol = trial["protocol"]
    level = claim["evidenceLevel"]
    trial_start = parse_timestamp(trial["startedAt"])
    trial_end = parse_timestamp(trial["completedAt"])
    recorded_at = parse_timestamp(record["recordedAt"])
    review_due = parse_timestamp(record["freshness"]["reviewDueAt"])

    if claim["policyVersion"] != policy["policyVersion"]:
        result.error(
            f"claim policy {claim['policyVersion']!r} does not match loaded policy {policy['policyVersion']!r}"
        )
    if record["schemaVersion"] != policy["schemaVersion"]:
        result.error("record schemaVersion does not match policy schemaVersion")
    if trial_start > trial_end:
        result.error("trial.startedAt must not be after trial.completedAt")
    if recorded_at < trial_end:
        result.error("recordedAt must be on or after trial.completedAt")
    if recorded_at > as_of:
        result.error("recordedAt must not be in the future relative to --as-of")
    if review_due <= trial_end:
        result.error("freshness.reviewDueAt must be after trial.completedAt")
    if as_of < trial_end:
        result.error("trial is in the future relative to --as-of")

    task = record["task"]
    claimed_digest = task["skill"]["sha256"]
    skill_path_value = task["skill"].get("path")
    catalog_task = task_catalog.get(task["slug"])
    if catalog_task is None:
        result.error(f"task slug {task['slug']!r} is absent from the built task catalog")
    else:
        if "sourceSha256" in catalog_task:
            source_digest = catalog_task["sourceSha256"]
            if source_digest is None:
                result.error(
                    "built catalog explicitly marks sourceSha256 unavailable; "
                    "evidence cannot qualify for this task"
                )
            elif not isinstance(source_digest, str) or not re.fullmatch(r"[a-f0-9]{64}", source_digest):
                result.error("built catalog sourceSha256 is not a lowercase SHA-256 digest")
            elif source_digest != claimed_digest:
                result.stale(
                    "current built skill SHA-256 differs from the tested revision "
                    "(exact resolved source digest)"
                )
        elif not skill_path_value:
            # Legacy/pathless catalogs predate sourceSha256. Hashing their
            # stored content is deterministic, but it is explicitly a fallback
            # because that presentation field may have normalized whitespace.
            catalog_content = catalog_task.get("content")
            if isinstance(catalog_content, str):
                current_digest = hashlib.sha256(catalog_content.encode("utf-8")).hexdigest()
                result.warning(
                    "built catalog lacks sourceSha256; used deterministic legacy content digest"
                )
                if current_digest != claimed_digest:
                    result.stale(
                        "current built skill SHA-256 differs from the tested revision "
                        "(legacy catalog-content fallback)"
                    )
            else:
                result.error("pathless task skill digest cannot be checked from the built catalog")
    revision = task["skill"]["revision"]
    if MUTABLE_VERSION.fullmatch(revision):
        result.error("task.skill.revision must be immutable, not a branch or moving alias")
    if skill_path_value:
        skill_path = (repo_root / skill_path_value).resolve()
        try:
            skill_path.relative_to(repo_root.resolve())
        except ValueError:
            result.error("task.skill.path escapes the repository root")
        else:
            if not skill_path.exists():
                result.stale(f"tested skill path no longer exists: {skill_path_value}")
            elif sha256_file(skill_path) != task["skill"]["sha256"]:
                result.stale("current skill SHA-256 differs from the tested revision")

    required_triggers = set(policy["requiredMaterialChangeTriggers"])
    actual_triggers = set(record["freshness"]["materialChangeTriggers"])
    missing_triggers = sorted(required_triggers - actual_triggers)
    if missing_triggers:
        result.error(f"freshness is missing material-change triggers: {', '.join(missing_triggers)}")

    max_age = timedelta(days=policy["freshnessDays"][level])
    policy_due = trial_end + max_age
    effective_due = min(review_due, policy_due)
    result.expires_at = effective_due
    if review_due > policy_due:
        result.warning(
            f"reviewDueAt exceeds the {level} policy window; effective expiry is {policy_due.isoformat()}"
        )
    if as_of > effective_due:
        result.stale(f"evidence expired at {effective_due.isoformat()}")

    artifacts = record["artifacts"]
    artifact_ids = [artifact["artifactId"] for artifact in artifacts]
    if len(artifact_ids) != len(set(artifact_ids)):
        result.error("artifactId values must be unique within a record")
    known_artifacts = set(artifact_ids)
    artifact_by_id = {artifact["artifactId"]: artifact for artifact in artifacts}
    artifact_status_by_id = {
        artifact["artifactId"]: artifact_verification_status(artifact, repo_root)
        for artifact in artifacts
    }
    result.artifact_verification = [
        {"artifactId": artifact_id, "status": artifact_status_by_id[artifact_id]}
        for artifact_id in sorted(artifact_status_by_id)
    ]
    for artifact in artifacts:
        parsed_uri = urlparse(artifact["uri"])
        content, _ = load_artifact_bytes(artifact, repo_root)
        sensitive_keys = {
            key.lower().replace("-", "_")
            for key, _ in parse_qsl(parsed_uri.query, keep_blank_values=True)
            if key.lower().replace("-", "_") in {
                item.replace("-", "_") for item in SENSITIVE_QUERY_KEYS
            }
        }
        if parsed_uri.username or parsed_uri.password or parsed_uri.fragment or sensitive_keys:
            result.error(f"artifact {artifact['artifactId']!r} URI appears to contain a secret or signed fragment")
        if artifact["containsSensitiveData"] and artifact["access"] == "public":
            result.error(f"sensitive artifact {artifact['artifactId']!r} cannot have public access")
        if artifact["containsSensitiveData"] and artifact["redaction"] == "none-needed":
            result.error(f"sensitive artifact {artifact['artifactId']!r} must be redacted or not-shareable")
        if content is not None:
            text_content = content.decode("utf-8", errors="ignore")
            if text_contains_secret(text_content):
                result.error(f"artifact {artifact['artifactId']!r} bytes contain a credential pattern")
            if any(pattern.search(text_content) for pattern in PII_PATTERNS):
                result.error(f"artifact {artifact['artifactId']!r} bytes contain potential PII")
            if artifact["access"] != "public" or artifact["containsSensitiveData"]:
                result.error(
                    f"artifact {artifact['artifactId']!r} embeds non-public bytes in the public repository"
                )
        if not parsed_uri.scheme:
            artifact_path = (repo_root / artifact["uri"]).resolve()
            try:
                artifact_path.relative_to(repo_root.resolve())
            except ValueError:
                result.error(f"artifact {artifact['artifactId']!r} URI escapes the repository root")
            else:
                if not artifact_path.exists():
                    result.error(f"local artifact {artifact['artifactId']!r} does not exist")
                elif sha256_file(artifact_path) != artifact["sha256"]:
                    result.error(f"local artifact {artifact['artifactId']!r} SHA-256 does not match")
        privacy_review_id = artifact.get("privacyReviewArtifactId")
        if artifact["containsSensitiveData"] and not privacy_review_id:
            result.error(f"sensitive artifact {artifact['artifactId']!r} needs privacyReviewArtifactId")
        if privacy_review_id:
            check_references(
                result, [privacy_review_id], known_artifacts,
                f"artifact {artifact['artifactId']!r} privacy review",
            )
            check_artifact_kinds(
                result, [privacy_review_id], artifact_by_id,
                {"evaluation", "log", "protocol"},
                f"artifact {artifact['artifactId']!r} privacy review",
            )

    cases = trial["cases"]
    case_ids = [case["caseId"] for case in cases]
    if len(case_ids) != len(set(case_ids)):
        result.error("caseId values must be unique within a record")
    for case in cases:
        check_references(result, case["inputArtifactIds"], known_artifacts, f"case {case['caseId']}")
        check_artifact_kinds(
            result, case["inputArtifactIds"], artifact_by_id, {"input"}, f"case {case['caseId']}"
        )
    case_input_fingerprints = {
        case["caseId"]: tuple(sorted(
            artifact_by_id[artifact_id]["sha256"]
            for artifact_id in case["inputArtifactIds"]
            if artifact_id in artifact_by_id
        ))
        for case in cases
    }
    if trial["caseDesign"] != "known-demonstration":
        fingerprint_to_cases: dict[tuple[str, ...], list[str]] = defaultdict(list)
        for case_id, fingerprint in case_input_fingerprints.items():
            fingerprint_to_cases[fingerprint].append(case_id)
        duplicate_inputs = [ids for ids in fingerprint_to_cases.values() if len(ids) > 1]
        if duplicate_inputs:
            result.error(
                "distinct trial cases reuse identical input artifact digests: "
                + "; ".join(", ".join(ids) for ids in duplicate_inputs)
            )
    expected_case_source = {
        "known-demonstration": "known",
        "repeated-cases": "known",
        "held-out": "held-out",
        "production": "production",
    }[trial["caseDesign"]]
    for case in cases:
        if case["sourceType"] != expected_case_source:
            result.error(
                f"case {case['caseId']!r} sourceType must be {expected_case_source!r} for {trial['caseDesign']!r} design"
            )

    criteria = protocol["acceptanceCriteria"]
    criterion_ids = [criterion["criterionId"] for criterion in criteria]
    if len(criterion_ids) != len(set(criterion_ids)):
        result.error("acceptance criterionId values must be unique")
    criterion_map = {criterion["criterionId"]: criterion for criterion in criteria}
    acceptance_policy = policy["acceptance"]
    if protocol["minimumWeightedScore"] < acceptance_policy["minimumWeightedScoreFloor"]:
        result.error(
            "protocol.minimumWeightedScore is below the policy floor of "
            f"{acceptance_policy['minimumWeightedScoreFloor']}"
        )
    if acceptance_policy.get("requiresCriticalCriterion") and not any(
        criterion["critical"] for criterion in criteria
    ):
        result.error("protocol needs at least one critical acceptance criterion")
    critical_failure_ids = [failure["failureId"] for failure in protocol["criticalFailures"]]
    if len(critical_failure_ids) != len(set(critical_failure_ids)):
        result.error("critical failureId values must be unique")
    known_failures = set(critical_failure_ids)
    preregistered = protocol["preRegisteredAt"]
    if preregistered is not None and parse_timestamp(preregistered) > trial_start:
        result.error("protocol.preRegisteredAt must be on or before trial.startedAt")

    production_ledger = record.get("production") or {}
    incident_ids = [incident["incidentId"] for incident in production_ledger.get("incidents", [])]
    if len(incident_ids) != len(set(incident_ids)):
        result.error("production incidentId values must be unique")
    known_incidents = set(incident_ids)

    stacks = record["testedStacks"]
    stack_ids = [stack["stackId"] for stack in stacks]
    if len(stack_ids) != len(set(stack_ids)):
        result.error("stackId values must be unique within a record")
    known_stacks = set(stack_ids)
    stack_by_id = {stack["stackId"]: stack for stack in stacks}
    immutable_stack_by_id: dict[str, bool] = {}
    for stack in stacks:
        model = stack["model"]
        stack_tested_at = parse_timestamp(stack["testedAt"])
        if stack_tested_at > trial_end:
            result.error(f"stack {stack['stackId']!r} was tested after the trial ended")
        if stack_tested_at > as_of:
            result.error(f"stack {stack['stackId']!r} testedAt is in the future")
        if MUTABLE_VERSION.fullmatch(model["version"]):
            result.error(f"stack {stack['stackId']!r} uses a moving model version alias")
        if MUTABLE_VERSION.fullmatch(stack["orchestrator"]["version"]):
            result.error(f"stack {stack['stackId']!r} uses a moving orchestrator version alias")
        for tool in stack["tools"]:
            if MUTABLE_VERSION.fullmatch(tool["version"]):
                result.error(f"stack {stack['stackId']!r} tool {tool['name']!r} uses a moving version alias")
        for permission in stack["permissions"]:
            approved_at = parse_timestamp(permission["approvedAt"])
            if approved_at > trial_end:
                result.error(
                    f"stack {stack['stackId']!r} permission for {permission['system']!r} "
                    "was approved after the trial ended"
                )
            if approved_at > as_of:
                result.error(f"stack {stack['stackId']!r} permission approval is in the future")
        check_references(
            result, stack["contextArtifactIds"], known_artifacts, f"stack {stack['stackId']} context"
        )
        check_artifact_kinds(
            result,
            stack["contextArtifactIds"],
            artifact_by_id,
            {"context", "protocol"},
            f"stack {stack['stackId']} context",
        )
        snapshot = stack["memory"].get("snapshotArtifactId")
        if snapshot:
            check_references(result, [snapshot], known_artifacts, f"stack {stack['stackId']} memory")
            check_artifact_kinds(
                result,
                [snapshot],
                artifact_by_id,
                {"context", "log"},
                f"stack {stack['stackId']} memory",
            )
        components = [stack["model"], stack["orchestrator"], *stack["tools"]]
        for component in components:
            release = component.get("immutableRelease") or {}
            release_artifact = release.get("artifactId")
            if release_artifact:
                check_references(
                    result,
                    [release_artifact],
                    known_artifacts,
                    f"stack {stack['stackId']} immutable release",
                )
                check_artifact_kinds(
                    result,
                    [release_artifact],
                    artifact_by_id,
                    {"context", "protocol", "log"},
                    f"stack {stack['stackId']} immutable release",
                )
        immutable_stack_by_id[stack["stackId"]] = stack_release_is_immutable(
            stack, artifact_by_id, artifact_status_by_id
        )

    arm_ids: set[str] = set()
    attempt_ids: set[str] = set()
    evaluated_cases_by_arm: dict[str, set[str]] = defaultdict(set)
    evaluated_attempts_by_arm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    attempted_cases_by_arm: dict[str, set[str]] = defaultdict(set)
    attempt_counts_by_arm_case: dict[str, Counter[str]] = defaultdict(Counter)
    arms_by_mode: dict[str, list[dict[str, Any]]] = defaultdict(list)
    evaluated_ai_attempts: list[dict[str, Any]] = []
    accepted_ai_attempts: list[dict[str, Any]] = []
    completed_attempts: list[dict[str, Any]] = []
    attempt_starts_by_case: dict[str, list[datetime]] = defaultdict(list)
    all_attempt_starts: list[datetime] = []
    auditable_attempt_ids: set[str] = set()
    referenced_artifacts_by_arm: dict[str, set[str]] = defaultdict(set)
    output_artifact_owner: dict[str, str] = {}
    output_digest_owner: dict[str, str] = {}
    receipt_artifact_owner: dict[str, str] = {}
    receipt_digest_owner: dict[str, str] = {}
    all_designated_receipt_ids = {
        criterion.get("receiptArtifactId")
        for arm in record["arms"]
        for attempt in arm["attempts"]
        for criterion in attempt["acceptance"]["criterionResults"]
        if criterion.get("receiptArtifactId")
    }
    attempt_identity_valid: dict[str, bool] = {}
    autonomy_consistent_attempt_ids: set[str] = set()
    for arm in record["arms"]:
        arm_id = arm["armId"]
        mode = arm["mode"]
        arms_by_mode[mode].append(arm)
        if arm_id in arm_ids:
            result.error(f"duplicate armId {arm_id!r}")
        arm_ids.add(arm_id)
        if mode in AI_MODES:
            if not arm.get("stackId"):
                result.error(f"{mode} arm {arm_id!r} must reference a tested stack")
            elif arm["stackId"] not in known_stacks:
                result.error(f"arm {arm_id!r} references unknown stack {arm['stackId']!r}")
        elif arm.get("stackId"):
            result.error(f"human-only arm {arm_id!r} must not reference an AI stack")
        if mode in {"human-only", "human-ai"} and not arm["operatorIds"]:
            result.error(f"{mode} arm {arm_id!r} needs at least one pseudonymous operator ID")

        arm_starts = [parse_timestamp(attempt["startedAt"]) for attempt in arm["attempts"]]
        if mode in AI_MODES and arm.get("stackId") in stack_by_id and arm_starts:
            stack = stack_by_id[arm["stackId"]]
            first_arm_start = min(arm_starts)
            if parse_timestamp(stack["testedAt"]) > first_arm_start:
                result.error(f"arm {arm_id!r} uses a stack tested after its first attempt began")
            for permission in stack["permissions"]:
                if parse_timestamp(permission["approvedAt"]) > first_arm_start:
                    result.error(
                        f"arm {arm_id!r} uses {permission['system']!r} permission approved "
                        "after its first attempt began"
                    )

        for attempt in arm["attempts"]:
            attempt_id = attempt["attemptId"]
            where = f"arm {arm_id!r} attempt {attempt_id!r}"
            if attempt_id in attempt_ids:
                result.error(f"duplicate attemptId {attempt_id!r}")
            attempt_ids.add(attempt_id)
            if attempt["caseId"] not in set(case_ids):
                result.error(f"{where} references unknown case {attempt['caseId']!r}")
            attempted_cases_by_arm[arm_id].add(attempt["caseId"])
            attempt_counts_by_arm_case[arm_id][attempt["caseId"]] += 1
            case = next((item for item in cases if item["caseId"] == attempt["caseId"]), None)
            if case:
                referenced_artifacts_by_arm[arm_id].update(case["inputArtifactIds"])
            attempt_start = parse_timestamp(attempt["startedAt"])
            attempt_end = parse_timestamp(attempt["completedAt"])
            if attempt_start > attempt_end:
                result.error(f"{where} starts after it completes")
            if attempt_start < trial_start or attempt_end > trial_end:
                result.error(f"{where} falls outside the trial window")
            attempt_starts_by_case[attempt["caseId"]].append(attempt_start)
            all_attempt_starts.append(attempt_start)
            check_references(result, attempt["outputArtifactIds"], known_artifacts, where)
            referenced_artifacts_by_arm[arm_id].update(attempt["outputArtifactIds"])
            attempt_identity_valid[attempt_id] = True
            for output_id in attempt["outputArtifactIds"]:
                output_artifact = artifact_by_id.get(output_id)
                prior_attempt = output_artifact_owner.setdefault(output_id, attempt_id)
                if prior_attempt != attempt_id:
                    attempt_identity_valid[attempt_id] = False
                    result.error(f"{where} reuses output artifact {output_id!r} from {prior_attempt!r}")
                if output_artifact:
                    digest = output_artifact["sha256"]
                    prior_digest_attempt = output_digest_owner.setdefault(digest, attempt_id)
                    if prior_digest_attempt != attempt_id:
                        attempt_identity_valid[attempt_id] = False
                        result.error(
                            f"{where} reuses output bytes from attempt {prior_digest_attempt!r}"
                        )
            check_artifact_kinds(
                result, attempt["outputArtifactIds"], artifact_by_id, {"output"}, where
            )

            acceptance = attempt["acceptance"]
            evaluated = attempt["status"] == "completed" and acceptance["overall"] != "not-evaluated"
            if attempt["status"] == "aborted" and acceptance["overall"] != "not-evaluated":
                result.error(f"{where} is aborted but has an evaluated outcome")
            if attempt["status"] == "completed":
                completed_attempts.append(attempt)
                if not attempt["outputArtifactIds"]:
                    result.error(f"{where} is completed but has no output artifact")
                if not attempt.get("measurements"):
                    result.error(f"{where} is completed but has no measurements")
            if mode in AI_MODES and attempt["status"] == "completed":
                measurements = attempt.get("measurements") or {}
                if "autonomousShare" not in measurements:
                    result.error(f"{where} needs autonomousShare for an AI-containing arm")

            if evaluated:
                if not acceptance.get("judgedAt") or not acceptance.get("evaluatorId"):
                    result.error(f"{where} has an evaluated outcome without evaluatorId and judgedAt")
                elif acceptance["evaluatorId"] != protocol["evaluator"]["id"]:
                    result.error(f"{where} evaluator differs from the preregistered evaluator")
                if acceptance.get("judgedAt"):
                    judged_at = parse_timestamp(acceptance["judgedAt"])
                    if judged_at < attempt_end:
                        result.error(f"{where} was judged before the attempt completed")
                    if judged_at > recorded_at:
                        result.error(f"{where} was judged after the evidence record was created")
                    if judged_at > as_of:
                        result.error(f"{where} judgment is in the future")
                result_ids = [item["criterionId"] for item in acceptance["criterionResults"]]
                receipts_valid = True
                if set(result_ids) != set(criterion_ids) or len(result_ids) != len(criterion_ids):
                    result.error(f"{where} must report every acceptance criterion exactly once")
                    receipts_valid = False
                else:
                    by_id = {item["criterionId"]: item for item in acceptance["criterionResults"]}
                    for item in by_id.values():
                        receipt_ids = item["evidenceArtifactIds"]
                        designated_receipt_id = item["receiptArtifactId"]
                        referenced_artifacts_by_arm[arm_id].update(receipt_ids)
                        if not item["evidenceArtifactIds"]:
                            result.error(
                                f"{where} criterion {item['criterionId']!r} has no auditable receipt"
                            )
                            receipts_valid = False
                        other_designated_receipts = (
                            all_designated_receipt_ids - {designated_receipt_id}
                        ).intersection(receipt_ids)
                        if other_designated_receipts:
                            result.error(
                                f"{where} criterion {item['criterionId']!r} uses another "
                                "criterion's evaluator receipt as auxiliary evidence"
                            )
                            receipts_valid = False
                        if designated_receipt_id not in receipt_ids:
                            result.error(
                                f"{where} criterion {item['criterionId']!r} designated receipt "
                                "is not listed in evidenceArtifactIds"
                            )
                            receipts_valid = False
                        if any(
                            artifact_id not in artifact_by_id
                            or artifact_by_id[artifact_id]["kind"] not in {"output", "evaluation", "log"}
                            or artifact_status_by_id.get(artifact_id) not in VERIFIED_ARTIFACT_STATUSES
                            for artifact_id in receipt_ids
                        ):
                            receipts_valid = False
                        for artifact_id in receipt_ids:
                            if artifact_status_by_id.get(artifact_id) == "claimed-only":
                                result.error(
                                    f"{where} criterion {item['criterionId']!r} receipt "
                                    f"{artifact_id!r} is claimed-only, not content-verifiable"
                                )
                        expected_receipt_sha = canonical_sha256(
                            criterion_receipt_payload(record, arm_id, attempt, item)
                        )
                        evaluator_issuer = policy.get("trustedEvaluatorIssuers", {}).get(
                            item.get("receiptIssuerId")
                        )
                        receipt_payload_bytes = canonical_json_bytes(
                            criterion_receipt_payload(record, arm_id, attempt, item)
                        )
                        if (
                            item.get("receiptIssuerId") != acceptance.get("evaluatorId")
                            or not evaluator_issuer
                            or evaluator_issuer.get("algorithm") != "rsa-pkcs1v15-sha256"
                            or not verify_rsa_pkcs1v15_sha256(
                                receipt_payload_bytes,
                                item.get("receiptSignature", ""),
                                evaluator_issuer.get("modulusHex", ""),
                                evaluator_issuer.get("exponent", 0),
                            )
                        ):
                            receipts_valid = False
                            result.error(f"{where} criterion receipt lacks a trusted evaluator signature")
                        matching_receipts = [designated_receipt_id] if (
                            designated_receipt_id in artifact_by_id
                            and artifact_by_id[designated_receipt_id]["kind"]
                            in {"evaluation", "log"}
                            and artifact_by_id[designated_receipt_id]["sha256"]
                            == expected_receipt_sha
                            and artifact_status_by_id.get(designated_receipt_id)
                            in VERIFIED_ARTIFACT_STATUSES
                        ) else []
                        if not matching_receipts:
                            receipts_valid = False
                            result.error(
                                f"{where} criterion {item['criterionId']!r} lacks an attempt-bound "
                                "evaluation receipt"
                            )
                        for receipt_id in matching_receipts:
                            receipt = artifact_by_id[receipt_id]
                            prior_attempt = receipt_artifact_owner.setdefault(receipt_id, attempt_id)
                            prior_digest_attempt = receipt_digest_owner.setdefault(
                                receipt["sha256"], attempt_id
                            )
                            if prior_attempt != attempt_id or prior_digest_attempt != attempt_id:
                                receipts_valid = False
                                result.error(f"{where} reuses an evaluation receipt from another attempt")
                        check_references(
                            result,
                            item["evidenceArtifactIds"],
                            known_artifacts,
                            f"{where} criterion {item['criterionId']!r}",
                        )
                        check_artifact_kinds(
                            result,
                            item["evidenceArtifactIds"],
                            artifact_by_id,
                            {"output", "evaluation", "log"},
                            f"{where} criterion {item['criterionId']!r}",
                        )
                    total_weight = sum(item["weight"] for item in criteria)
                    passed_weight = sum(
                        criterion_map[item_id]["weight"]
                        for item_id, item in by_id.items()
                        if item["result"] == "pass"
                    )
                    critical_passed = all(
                        by_id[item_id]["result"] == "pass"
                        for item_id, criterion in criterion_map.items()
                        if criterion["critical"]
                    )
                    complete_judgment = all(item["result"] != "not-evaluated" for item in by_id.values())
                    linked_critical_error = any(
                        error.get("criticalFailureId") in known_failures
                        for error in attempt["errors"]
                        if error.get("criticalFailureId")
                    )
                    policy_rejecting_error = any(
                        error["severity"] in set(acceptance_policy["rejectSeverities"])
                        for error in attempt["errors"]
                    )
                    computed_accept = (
                        complete_judgment
                        and critical_passed
                        and not linked_critical_error
                        and not policy_rejecting_error
                        and passed_weight / total_weight >= protocol["minimumWeightedScore"]
                    )
                    if (acceptance["overall"] == "accepted") != computed_accept:
                        result.error(
                            f"{where} overall acceptance disagrees with the weighted/critical protocol result"
                        )
                if receipts_valid and attempt_identity_valid.get(attempt_id, False):
                    auditable_attempt_ids.add(attempt_id)
                evaluated_cases_by_arm[arm_id].add(attempt["caseId"])
                evaluated_attempts_by_arm[arm_id].append(attempt)
                if mode in AI_MODES:
                    evaluated_ai_attempts.append(attempt)
                    if acceptance["overall"] == "accepted":
                        accepted_ai_attempts.append(attempt)

            labor = attempt["labor"]
            human_intervention_minutes = sum(
                intervention["minutes"]
                for intervention in labor["interventions"]
                if intervention["initiatedBy"] == "human"
            )
            if human_intervention_minutes > labor["supervisionMinutes"] + labor["operatorMinutes"]:
                result.error(f"{where} human intervention minutes exceed recorded active human time")
            if mode == "ai-only":
                if labor["operatorMinutes"] or labor["supervisionMinutes"] or human_intervention_minutes:
                    result.error(
                        f"{where} is AI-only but contains active human work; use reviewMinutes or Human+AI"
                    )
            if mode == "human-ai" and not (
                labor["operatorMinutes"] or labor["supervisionMinutes"] or human_intervention_minutes
            ):
                result.error(f"{where} is Human+AI but records no active human work")

            error_ids: set[str] = set()
            for error in attempt["errors"]:
                if error["errorId"] in error_ids:
                    result.error(f"{where} has duplicate errorId {error['errorId']!r}")
                error_ids.add(error["errorId"])
                check_references(result, error["evidenceArtifactIds"], known_artifacts, where)
                referenced_artifacts_by_arm[arm_id].update(error["evidenceArtifactIds"])
                check_artifact_kinds(
                    result,
                    error["evidenceArtifactIds"],
                    artifact_by_id,
                    {"output", "evaluation", "log"},
                    where,
                )
                failure_id = error.get("criticalFailureId")
                if error["severity"] in set(acceptance_policy["rejectSeverities"]) and not failure_id:
                    result.error(
                        f"{where} {error['severity']} error must reference a criticalFailureId"
                    )
                if failure_id and failure_id not in known_failures:
                    result.error(f"{where} references unknown critical failure {failure_id!r}")
                incident_id = error.get("incidentId")
                if trial["environment"] == "production" and error["detectedStage"] == "post-release":
                    if not incident_id:
                        result.error(f"{where} post-release production error needs incidentId")
                    elif incident_id not in known_incidents:
                        result.error(f"{where} references unknown production incident {incident_id!r}")
                recovery = error["recovery"]
                check_references(result, recovery["artifactIds"], known_artifacts, f"{where} recovery")
                referenced_artifacts_by_arm[arm_id].update(recovery["artifactIds"])
                check_artifact_kinds(
                    result,
                    recovery["artifactIds"],
                    artifact_by_id,
                    {"recovery", "output", "log"},
                    f"{where} recovery",
                )
                if not recovery["attempted"]:
                    if recovery["successful"] is not None or recovery["minutes"] != 0:
                        result.error(f"{where} unattempted recovery must have null success and zero minutes")
                elif recovery["successful"] is None or not recovery["action"].strip():
                    result.error(f"{where} attempted recovery needs a success result and action")

            if mode in AI_MODES and attempt["status"] == "completed":
                elapsed = max(
                    0.0,
                    (attempt_end - attempt_start).total_seconds() / 60,
                )
                recovery_minutes = sum(error["recovery"]["minutes"] for error in attempt["errors"])
                active_human = labor["operatorMinutes"] + labor["supervisionMinutes"]
                denominator = (
                    elapsed + labor["preparationMinutes"] + labor["reviewMinutes"]
                    + recovery_minutes
                )
                derived_autonomy = (
                    max(0.0, elapsed - active_human) / denominator if denominator else 0.0
                )
                declared_autonomy = (attempt.get("measurements") or {}).get("autonomousShare")
                if declared_autonomy is not None and abs(declared_autonomy - derived_autonomy) <= 0.02:
                    autonomy_consistent_attempt_ids.add(attempt_id)
                else:
                    result.error(
                        f"{where} autonomousShare is inconsistent with bound labor, elapsed time, "
                        "and recovery burden"
                    )

        if mode in AI_MODES and arm.get("stackId") in stack_by_id:
            stack = stack_by_id[arm["stackId"]]
            referenced_artifacts_by_arm[arm_id].update(stack["contextArtifactIds"])
            snapshot_id = stack["memory"].get("snapshotArtifactId")
            if snapshot_id:
                referenced_artifacts_by_arm[arm_id].add(snapshot_id)
            for component in [stack["model"], stack["orchestrator"], *stack["tools"]]:
                release_artifact_id = (component.get("immutableRelease") or {}).get("artifactId")
                if release_artifact_id:
                    referenced_artifacts_by_arm[arm_id].add(release_artifact_id)

        result.arm_metrics.append(arm_summary(arm))

    def arm_evidence_is_verifiable(arm_id: str) -> bool:
        return all(
            artifact_status_by_id.get(artifact_id) in VERIFIED_ARTIFACT_STATUSES
            for artifact_id in referenced_artifacts_by_arm[arm_id]
        )

    def evaluated_attempts_are_auditable(arm_id: str) -> bool:
        arm_mode = next(arm["mode"] for arm in record["arms"] if arm["armId"] == arm_id)
        return all(
            attempt["attemptId"] in auditable_attempt_ids
            and (
                arm_mode not in AI_MODES
                or attempt["attemptId"] in autonomy_consistent_attempt_ids
            )
            for attempt in evaluated_attempts_by_arm[arm_id]
        )

    heldout_integrity = True
    if trial["caseDesign"] == "held-out":
        for case in cases:
            where = f"held-out case {case['caseId']!r}"
            if case.get("contaminationCheck") != "passed":
                result.error(f"{where} needs a passed contamination check")
                heldout_integrity = False
            released_at = case.get("releasedAt")
            if not released_at:
                result.error(f"{where} needs releasedAt")
                heldout_integrity = False
                continue
            released = parse_timestamp(released_at)
            starts = attempt_starts_by_case.get(case["caseId"], [])
            if released < trial_start:
                result.error(f"{where} was released before the preregistered trial began")
                heldout_integrity = False
            if starts and released > min(starts):
                result.error(f"{where} was released after an attempt had already begun")
                heldout_integrity = False

    externally_bound_preregistration = False
    preregistration = protocol.get("preregistration")
    if preregistration:
        prereg_errors: list[str] = []
        protocol_artifact_id = preregistration["protocolArtifactId"]
        protocol_artifact = artifact_by_id.get(protocol_artifact_id)
        if not protocol_artifact:
            prereg_errors.append("protocolArtifactId is unknown")
        elif protocol_artifact["kind"] != "protocol":
            prereg_errors.append("protocolArtifactId is not a protocol artifact")
        expected_protocol_digest = protocol_binding_digest(record)
        if preregistration["protocolSha256"] != expected_protocol_digest:
            prereg_errors.append("protocolSha256 does not bind the acceptance criteria and assignment")
        if protocol_artifact and protocol_artifact["sha256"] != expected_protocol_digest:
            prereg_errors.append("protocol artifact digest does not match the bound protocol")
        if artifact_status_by_id.get(protocol_artifact_id) not in VERIFIED_ARTIFACT_STATUSES:
            prereg_errors.append("protocol artifact is claimed-only, not content-verifiable")
        published_at = parse_timestamp(preregistration["publishedAt"])
        first_attempt = min(all_attempt_starts) if all_attempt_starts else trial_start
        if published_at >= first_attempt:
            prereg_errors.append("external publication must predate the first trial attempt")
        if preregistered is None or parse_timestamp(preregistered) != published_at:
            prereg_errors.append("preRegisteredAt must equal the externally bound publication timestamp")
        binding = preregistration["binding"]
        immutable_ref = binding["immutableRef"]
        if binding["kind"] == "git-commit":
            if not re.fullmatch(r"[0-9a-f]{40}", immutable_ref):
                prereg_errors.append("git preregistration needs a full 40-character commit SHA")
            prereg_errors.append(
                "git commit timestamp/path verification is unavailable; use a trusted signed receipt"
            )
        else:
            receipt_id = binding.get("receiptArtifactId")
            receipt = artifact_by_id.get(receipt_id) if receipt_id else None
            issuer_id = binding.get("issuerId")
            issuer = policy.get("trustedReceiptIssuers", {}).get(issuer_id)
            receipt_payload = canonical_json_bytes(
                preregistration_receipt_payload(record, preregistration)
            )
            expected_receipt_sha = hashlib.sha256(receipt_payload).hexdigest()
            if not receipt:
                prereg_errors.append("signed preregistration needs a receiptArtifactId")
            elif immutable_ref != f"sha256:{receipt['sha256']}":
                prereg_errors.append("signed receipt immutableRef does not match its artifact digest")
            elif receipt["sha256"] != expected_receipt_sha:
                prereg_errors.append("signed receipt bytes do not bind protocol and publication time")
            elif receipt["kind"] not in {"protocol", "log", "evaluation"}:
                prereg_errors.append("signed receipt artifact has an unsupported kind")
            elif artifact_status_by_id.get(receipt_id) not in VERIFIED_ARTIFACT_STATUSES:
                prereg_errors.append("signed receipt artifact is not content-verifiable")
            if not issuer or issuer.get("algorithm") != "rsa-pkcs1v15-sha256":
                prereg_errors.append("signed receipt issuer is not trusted by this policy")
            elif not verify_rsa_pkcs1v15_sha256(
                receipt_payload,
                binding.get("signature", ""),
                issuer.get("modulusHex", ""),
                issuer.get("exponent", 0),
            ):
                prereg_errors.append("signed receipt signature verification failed")
        if prereg_errors:
            for message in prereg_errors:
                result.error(f"preregistration: {message}")
        else:
            externally_bound_preregistration = True

    evaluator_id = protocol["evaluator"]["id"]
    identity_conflicts = {
        operator_id
        for arm in record["arms"]
        for operator_id in arm["operatorIds"]
    }
    identity_conflicts.add(record["recordedBy"]["id"])
    if record.get("production"):
        identity_conflicts.add(record["production"]["accountableOwnerId"])
    evaluator_identity_independent = evaluator_id not in identity_conflicts
    if (
        protocol["evaluator"]["independence"] in {"peer", "independent"}
        and not evaluator_identity_independent
    ):
        result.error(
            "evaluator independence label conflicts with an operator, recorder, or accountable owner ID"
        )

    all_case_ids = set(case_ids)
    arm_by_id = {arm["armId"]: arm for arm in record["arms"]}
    metrics_by_arm_id = {metric["armId"]: metric for metric in result.arm_metrics}
    gates: dict[str, tuple[bool, list[str]]] = {}

    e1 = policy["qualification"]["E1"]
    e1_reasons: list[str] = []
    e1_candidate_arms = sorted(
        arm["armId"]
        for arm in record["arms"]
        if arm["mode"] in AI_MODES
        and sum(
            attempt["acceptance"]["overall"] == "accepted"
            for attempt in evaluated_attempts_by_arm[arm["armId"]]
        ) >= e1["minimumAcceptedAiAttempts"]
        and evaluated_attempts_are_auditable(arm["armId"])
        and arm_evidence_is_verifiable(arm["armId"])
        and (
            not e1.get("requiresImmutableStack")
            or immutable_stack_by_id.get(arm.get("stackId"), False)
        )
    )
    if trial["caseDesign"] not in e1["allowedCaseDesigns"]:
        e1_reasons.append("case design is not allowed")
    if not e1_candidate_arms:
        e1_reasons.append(
            "no single AI-containing arm has an accepted attempt plus auditable receipts, "
            "content-verifiable evidence, and immutable stack provenance"
        )
    gates["E1"] = (not e1_reasons, e1_reasons)

    e2 = policy["qualification"]["E2"]
    e2_reasons: list[str] = []
    if trial["caseDesign"] not in e2["allowedCaseDesigns"]:
        e2_reasons.append("trial is not repeated-case or held-out")
    if trial["caseDesign"] == "held-out" and not heldout_integrity:
        e2_reasons.append("held-out integrity checks failed")
    if e2.get("requiresPreregistration") and preregistered is None:
        e2_reasons.append("protocol was not preregistered")
    if e2.get("requiresExternallyBoundPreregistration") and not externally_bound_preregistration:
        e2_reasons.append("protocol lacks an externally bound preregistration receipt")
    e2_candidate_arms: list[str] = []
    for arm in record["arms"]:
        if arm["mode"] not in AI_MODES:
            continue
        arm_id = arm["armId"]
        evaluated_attempts = evaluated_attempts_by_arm[arm_id]
        candidate_ok = (
            len(evaluated_cases_by_arm[arm_id]) >= e2["minimumDistinctCases"]
            and len(evaluated_attempts) >= e2["minimumEvaluatedAiAttempts"]
            and measurements_complete(evaluated_attempts, e2["requiredAiMeasurements"])
            and evaluated_attempts_are_auditable(arm_id)
            and arm_evidence_is_verifiable(arm_id)
        )
        if e2.get("requiresCompleteCaseCoverage"):
            candidate_ok = candidate_ok and attempted_cases_by_arm[arm_id] == all_case_ids
        maximum_attempts = e2.get("maximumAttemptsPerCasePerArm")
        if maximum_attempts is not None:
            candidate_ok = candidate_ok and all(
                count <= maximum_attempts
                for count in attempt_counts_by_arm_case[arm_id].values()
            )
        if e2.get("requiresImmutableStack"):
            candidate_ok = candidate_ok and immutable_stack_by_id.get(arm.get("stackId"), False)
        if candidate_ok:
            e2_candidate_arms.append(arm_id)
    e2_candidate_arms.sort()
    if not e2_candidate_arms:
        e2_reasons.append(
            "no single AI-containing arm has enough distinct evaluated cases, required measurements, "
            "immutable stack provenance, complete preregistered case coverage, and allowed attempt counts"
        )
    gates["E2"] = (not e2_reasons, e2_reasons)

    e3 = policy["qualification"]["E3"]
    e3_reasons: list[str] = []
    arm_modes = {arm["mode"] for arm in record["arms"]}
    if trial["caseDesign"] not in e3["allowedCaseDesigns"]:
        e3_reasons.append("case design is not comparative")
    if protocol["assignment"] not in e3["allowedAssignments"]:
        e3_reasons.append("assignment is not paired, randomized, or counterbalanced")
    if protocol["evaluator"]["independence"] not in e3["allowedEvaluatorIndependence"]:
        e3_reasons.append("evaluator is not peer or independent")
    if not evaluator_identity_independent:
        e3_reasons.append("evaluator ID is not independent from trial operators or owners")
    if e3.get("requiresBlindedEvaluator") and not protocol["evaluator"]["blinded"]:
        e3_reasons.append("evaluator is not blinded to arm assignment")
    if trial["caseDesign"] == "held-out" and not heldout_integrity:
        e3_reasons.append("held-out integrity checks failed")
    if e3.get("requiresPreregistration") and preregistered is None:
        e3_reasons.append("protocol was not preregistered")
    if e3.get("requiresExternallyBoundPreregistration") and not externally_bound_preregistration:
        e3_reasons.append("protocol lacks an externally bound preregistration receipt")
    required_modes = set(e3["requiredArmModes"])
    if not required_modes.issubset(arm_modes):
        e3_reasons.append("Human-only, AI-only, and Human+AI arms are all required")
    primary_comparison = protocol.get("primaryComparison")
    primary_ids: tuple[str, str, str] | None = None
    if e3.get("requiresPreregisteredPrimaryComparison"):
        if not primary_comparison:
            e3_reasons.append("protocol lacks a preregistered primary three-arm comparison")
        else:
            primary_ids = (
                primary_comparison["humanOnlyArmId"],
                primary_comparison["aiOnlyArmId"],
                primary_comparison["humanAiArmId"],
            )
            for arm_id, expected_mode in zip(
                primary_ids, ("human-only", "ai-only", "human-ai")
            ):
                arm = arm_by_id.get(arm_id)
                if not arm or arm["mode"] != expected_mode:
                    result.error(
                        f"primary comparison {arm_id!r} is not a declared {expected_mode} arm"
                    )
                    e3_reasons.append("preregistered primary comparison references the wrong arm modes")

    all_comparisons: list[dict[str, Any]] = []
    for human_arm, ai_arm, combined_arm in product(
        arms_by_mode["human-only"], arms_by_mode["ai-only"], arms_by_mode["human-ai"]
    ):
        ids = (human_arm["armId"], ai_arm["armId"], combined_arm["armId"])
        intersection = set.intersection(*(evaluated_cases_by_arm[arm_id] for arm_id in ids))
        all_comparisons.append({
            "human": human_arm,
            "ai": ai_arm,
            "combined": combined_arm,
            "armIds": ids,
            "caseIds": intersection,
        })
    matched_comparisons = list(all_comparisons)
    if e3.get("requiresMatchedAiStack"):
        matched_comparisons = [
            comparison for comparison in matched_comparisons
            if comparison["ai"].get("stackId") == comparison["combined"].get("stackId")
        ]
        if all_comparisons and not matched_comparisons:
            e3_reasons.append("AI-only and Human+AI arms do not share a tested stack")
    if e3.get("requiresImmutableStack"):
        matched_comparisons = [
            comparison for comparison in matched_comparisons
            if immutable_stack_by_id.get(comparison["ai"].get("stackId"), False)
            and immutable_stack_by_id.get(comparison["combined"].get("stackId"), False)
        ]
    if e3.get("requiresMatchedCaseSets"):
        matched_comparisons = [
            comparison for comparison in matched_comparisons
            if all(
                evaluated_cases_by_arm[arm_id] == comparison["caseIds"]
                for arm_id in comparison["armIds"]
            )
        ]
        if all_comparisons and not matched_comparisons:
            e3_reasons.append("comparison arms do not have identical evaluated case sets")
    if e3.get("requiresCompleteCaseCoverage"):
        matched_comparisons = [
            comparison for comparison in matched_comparisons
            if all(attempted_cases_by_arm[arm_id] == all_case_ids for arm_id in comparison["armIds"])
        ]
        if all_comparisons and not matched_comparisons:
            e3_reasons.append("comparison arms do not cover every preregistered case")
    maximum_attempts = e3.get("maximumAttemptsPerCasePerArm")
    if maximum_attempts is not None:
        matched_comparisons = [
            comparison for comparison in matched_comparisons
            if all(
                count <= maximum_attempts
                for arm_id in comparison["armIds"]
                for count in attempt_counts_by_arm_case[arm_id].values()
            )
        ]
    matched_comparisons = [
        comparison for comparison in matched_comparisons
        if len(comparison["caseIds"]) >= e3["minimumMatchedCasesPerArm"]
        and measurements_complete(
            evaluated_attempts_by_arm[comparison["human"]["armId"]],
            e3["requiredHumanMeasurements"],
        )
        and all(
            measurements_complete(
                evaluated_attempts_by_arm[comparison[key]["armId"]],
                e3["requiredAiMeasurements"],
            )
            for key in ("ai", "combined")
        )
        and all(
            evaluated_attempts_are_auditable(comparison[key]["armId"])
            and arm_evidence_is_verifiable(comparison[key]["armId"])
            for key in ("human", "ai", "combined")
        )
    ]
    if not matched_comparisons:
        e3_reasons.append("no fully qualified matched three-arm comparison remains")
    matched_comparisons.sort(
        key=lambda comparison: (
            -len(comparison["caseIds"]),
            comparison["human"]["armId"],
            comparison["ai"]["armId"],
            comparison["combined"]["armId"],
        )
    )
    if primary_ids:
        selected_comparison = next(
            (
                comparison
                for comparison in matched_comparisons
                if comparison["armIds"] == primary_ids
            ),
            None,
        )
        if selected_comparison is None:
            e3_reasons.append("preregistered primary comparison is not fully qualified")
    else:
        selected_comparison = matched_comparisons[0] if matched_comparisons else None
    gates["E3"] = (not e3_reasons, e3_reasons)

    e4 = policy["qualification"]["E4"]
    e4_reasons: list[str] = []
    production = record.get("production")
    production_start = date.fromisoformat(production["periodStart"]) if production else None
    production_end = date.fromisoformat(production["periodEnd"]) if production else None
    downstream_receipts_verifiable = True
    e4_outcome_verdict_by_arm: dict[str, bool] = {}
    production_ledger_verifiable = False
    if trial["environment"] != e4["requiresEnvironment"]:
        e4_reasons.append("environment is not production")
    if trial["caseDesign"] != e4["requiresCaseDesign"]:
        e4_reasons.append("case design is not production")
    if e4.get("requiresPreregistration") and preregistered is None:
        e4_reasons.append("production sampling/deployment plan was not preregistered")
    if e4.get("requiresExternallyBoundPreregistration") and not externally_bound_preregistration:
        e4_reasons.append("production plan lacks a trusted signed preregistration receipt")
    if not production:
        e4_reasons.append("production ledger is missing")
    else:
        calendar_days = (production_end - production_start).days + 1
        if production_start > production_end:
            result.error("production.periodStart must not be after periodEnd")
        if production_start < trial_start.date() or production_end > trial_end.date():
            result.error("production period must be contained in the recorded trial window")
            e4_reasons.append("production period falls outside the trial window")
        if calendar_days < e4["minimumCalendarDays"]:
            e4_reasons.append("production period is not sustained for enough calendar days")
        if e4.get("requiresAccountableOwner") and not production["accountableOwnerId"]:
            e4_reasons.append("accountable production owner is missing")
        if e4.get("requiresDownstreamOutcome") and not production["downstreamOutcomes"]:
            e4_reasons.append("downstream production outcome is missing")
        if e4.get("requiresIncidentLedger") and "incidents" not in production:
            e4_reasons.append("production incident ledger is missing")
        sampling_id = production["samplingFrameArtifactId"]
        event_ledger_id = production["eventLedgerArtifactId"]
        sampling_artifact = artifact_by_id.get(sampling_id)
        event_artifact = artifact_by_id.get(event_ledger_id)
        expected_sampling_sha = canonical_sha256(sampling_frame_payload(record))
        expected_event_sha = canonical_sha256(production_event_ledger_payload(record))
        production_issuer = policy.get("trustedProductionDataIssuers", {}).get(
            production.get("eventLedgerIssuerId")
        )
        event_signature_valid = bool(
            production_issuer
            and production_issuer.get("algorithm") == "rsa-pkcs1v15-sha256"
            and verify_rsa_pkcs1v15_sha256(
                canonical_json_bytes(production_event_ledger_payload(record)),
                production.get("eventLedgerSignature", ""),
                production_issuer.get("modulusHex", ""),
                production_issuer.get("exponent", 0),
            )
        )
        sampling_valid = bool(
            sampling_artifact
            and sampling_artifact["kind"] in {"protocol", "log"}
            and sampling_artifact["sha256"] == expected_sampling_sha
            and artifact_status_by_id.get(sampling_id) in VERIFIED_ARTIFACT_STATUSES
        )
        event_valid = bool(
            event_artifact
            and event_artifact["kind"] == "log"
            and event_artifact["sha256"] == expected_event_sha
            and artifact_status_by_id.get(event_ledger_id) in VERIFIED_ARTIFACT_STATUSES
            and event_signature_valid
        )
        production_ledger_verifiable = sampling_valid and event_valid
        if e4.get("requiresSamplingFrame") and not sampling_valid:
            e4_reasons.append("production sampling frame is not byte-verified and plan-bound")
        if e4.get("requiresEventLedger") and not event_valid:
            e4_reasons.append(
                "production event ledger is not byte-verified, attempt-complete, and signed "
                "by a trusted production-data issuer"
            )
            if not event_signature_valid:
                result.error("production event ledger lacks a trusted production-data signature")
        for outcome in production["downstreamOutcomes"]:
            outcome_start = date.fromisoformat(outcome["periodStart"])
            outcome_end = date.fromisoformat(outcome["periodEnd"])
            if outcome_start > outcome_end:
                result.error(f"production outcome {outcome['metric']!r} starts after it ends")
            if outcome_end < production_start:
                result.error(
                    f"production outcome {outcome['metric']!r} neither overlaps nor follows production"
                )
            if outcome_end > recorded_at.date() or outcome_end > as_of.date():
                result.error(f"production outcome {outcome['metric']!r} ends in the future")
            if any(
                artifact_status_by_id.get(artifact_id) not in VERIFIED_ARTIFACT_STATUSES
                for artifact_id in outcome["evidenceArtifactIds"]
            ):
                downstream_receipts_verifiable = False
                result.error(
                    f"production outcome {outcome['metric']!r} has a claimed-only evidence receipt"
                )
            outcome_payload_bytes = canonical_json_bytes(
                downstream_outcome_payload(record, outcome)
            )
            expected_outcome_sha = hashlib.sha256(outcome_payload_bytes).hexdigest()
            outcome_issuer = policy.get("trustedOutcomeIssuers", {}).get(
                outcome.get("outcomeIssuerId")
            )
            outcome_signature_valid = bool(
                outcome_issuer
                and outcome_issuer.get("algorithm") == "rsa-pkcs1v15-sha256"
                and verify_rsa_pkcs1v15_sha256(
                    outcome_payload_bytes,
                    outcome.get("outcomeSignature", ""),
                    outcome_issuer.get("modulusHex", ""),
                    outcome_issuer.get("exponent", 0),
                )
            )
            if not outcome_signature_valid:
                downstream_receipts_verifiable = False
                result.error(
                    f"production outcome {outcome['metric']!r} lacks a trusted "
                    "outcome-issuer signature"
                )
            if not any(
                artifact_id in artifact_by_id
                and artifact_by_id[artifact_id]["sha256"] == expected_outcome_sha
                and artifact_status_by_id.get(artifact_id) in VERIFIED_ARTIFACT_STATUSES
                for artifact_id in outcome["evidenceArtifactIds"]
            ):
                downstream_receipts_verifiable = False
                result.error(
                    f"production outcome {outcome['metric']!r} lacks a deployment/arm-bound receipt"
                )
            outcome_passed = (
                outcome["value"] >= outcome["target"] and outcome["value"] >= outcome["baseline"]
                if outcome["direction"] == "increase"
                else outcome["value"] <= outcome["target"] and outcome["value"] <= outcome["baseline"]
            )
            e4_outcome_verdict_by_arm[outcome["armId"]] = (
                e4_outcome_verdict_by_arm.get(outcome["armId"], True) and outcome_passed
            )
            check_references(
                result,
                outcome["evidenceArtifactIds"],
                known_artifacts,
                f"production outcome {outcome['metric']!r}",
            )
            check_artifact_kinds(
                result,
                outcome["evidenceArtifactIds"],
                artifact_by_id,
                {"downstream", "evaluation"},
                f"production outcome {outcome['metric']!r}",
            )
        for incident in production["incidents"]:
            discovered_at = parse_timestamp(incident["discoveredAt"])
            if discovered_at < trial_start or discovered_at > recorded_at:
                result.error(
                    f"production incident {incident['incidentId']!r} discovery falls outside "
                    "the trial-to-record window"
                )
            if not production_start <= discovered_at.date() <= production_end:
                result.error(
                    f"production incident {incident['incidentId']!r} falls outside the "
                    "declared production period"
                )
            if incident["deploymentId"] != production["deploymentId"]:
                result.error(f"production incident {incident['incidentId']!r} deploymentId mismatches")
            incident_arm = arm_by_id.get(incident["armId"])
            if not incident_arm or incident_arm.get("stackId") != incident["stackId"]:
                result.error(f"production incident {incident['incidentId']!r} arm/stack binding mismatches")
            elif not set(incident["attemptIds"]).issubset({
                attempt["attemptId"] for attempt in incident_arm["attempts"]
            }):
                result.error(f"production incident {incident['incidentId']!r} references another arm's attempts")
            check_references(
                result,
                incident.get("recoveryArtifactIds", []),
                known_artifacts,
                f"production incident {incident['incidentId']!r}",
            )
            check_artifact_kinds(
                result,
                incident.get("recoveryArtifactIds", []),
                artifact_by_id,
                {"recovery", "log", "output"},
                f"production incident {incident['incidentId']!r}",
            )

    e4_candidate_arms: list[str] = []
    for arm in record["arms"]:
        if arm["mode"] not in AI_MODES:
            continue
        arm_id = arm["armId"]
        evaluated_attempts = evaluated_attempts_by_arm[arm_id]
        first_attempt = min(
            (parse_timestamp(attempt["startedAt"]).date() for attempt in evaluated_attempts),
            default=None,
        )
        last_attempt = max(
            (parse_timestamp(attempt["completedAt"]).date() for attempt in evaluated_attempts),
            default=None,
        )
        observed_days = (
            (last_attempt - first_attempt).days + 1 if first_attempt and last_attempt else 0
        )
        candidate_ok = (
            len(evaluated_cases_by_arm[arm_id]) >= e4["minimumProductionCases"]
            and measurements_complete(evaluated_attempts, e4["requiredAiMeasurements"])
            and observed_days >= e4["minimumCalendarDays"]
            and evaluated_attempts_are_auditable(arm_id)
            and arm_evidence_is_verifiable(arm_id)
            and downstream_receipts_verifiable
            and production_ledger_verifiable
        )
        candidate_attempt_ids = {attempt["attemptId"] for attempt in evaluated_attempts}
        linked_outcomes = [
            outcome for outcome in (production or {}).get("downstreamOutcomes", [])
            if outcome["armId"] == arm_id
            and outcome["stackId"] == arm.get("stackId")
            and set(outcome["attemptIds"]) == candidate_attempt_ids
        ]
        candidate_ok = candidate_ok and bool(linked_outcomes)
        linked_incidents = [
            incident for incident in (production or {}).get("incidents", [])
            if incident["armId"] == arm_id and incident["stackId"] == arm.get("stackId")
        ]
        if any(incident["severity"] in {"S3", "S4"} for incident in linked_incidents):
            e4_outcome_verdict_by_arm[arm_id] = False
        if production_start and production_end and first_attempt and last_attempt:
            candidate_ok = candidate_ok and (
                production_start <= first_attempt <= last_attempt <= production_end
            )
        if e4.get("requiresCompleteCaseCoverage"):
            candidate_ok = candidate_ok and attempted_cases_by_arm[arm_id] == all_case_ids
        maximum_attempts = e4.get("maximumAttemptsPerCasePerArm")
        if maximum_attempts is not None:
            candidate_ok = candidate_ok and all(
                count <= maximum_attempts
                for count in attempt_counts_by_arm_case[arm_id].values()
            )
        if e4.get("requiresAttemptCost"):
            candidate_ok = candidate_ok and all("cost" in attempt for attempt in evaluated_attempts)
        if e4.get("requiresImmutableStack"):
            candidate_ok = candidate_ok and immutable_stack_by_id.get(arm.get("stackId"), False)
        if candidate_ok:
            e4_candidate_arms.append(arm_id)
    e4_candidate_arms.sort()
    if not e4_candidate_arms:
        e4_reasons.append(
            "no single production AI-containing arm independently satisfies case count, sustained span, "
            "cost, measurements, immutable stack provenance, and complete coverage"
        )
    gates["E4"] = (not e4_reasons, e4_reasons)

    e3_ai_ids = sorted({
        comparison[key]["armId"]
        for comparison in matched_comparisons
        for key in ("ai", "combined")
    })
    result.qualifying_ai_arm_ids = {
        "E1": e1_candidate_arms,
        "E2": e2_candidate_arms,
        "E3": e3_ai_ids,
        "E4": e4_candidate_arms,
    }
    result.qualified_levels = [gate_level for gate_level, (passed, _) in gates.items() if passed]
    claimed_passed, claimed_reasons = gates[level]
    if not claimed_passed:
        result.error(f"{level} evidence overclaim: {'; '.join(claimed_reasons)}")

    if level == "E3" and selected_comparison:
        result.selected_ai_arm_ids = [
            selected_comparison["ai"]["armId"],
            selected_comparison["combined"]["armId"],
        ]
        result.selected_public_arm_ids = list(selected_comparison["armIds"])
    else:
        result.selected_ai_arm_ids = list(result.qualifying_ai_arm_ids.get(level, []))
        result.selected_public_arm_ids = list(result.selected_ai_arm_ids)
    selected_public = set(result.selected_public_arm_ids)
    result.public_arm_metrics = [
        metric for metric in result.arm_metrics if metric["armId"] in selected_public
    ]
    selected_ai_metrics = [
        metrics_by_arm_id[arm_id]
        for arm_id in result.selected_ai_arm_ids
        if arm_id in metrics_by_arm_id
    ]
    minimum_rate = acceptance_policy["supportsCapabilityMinimumAcceptanceRate"]
    result.derived_interpretation = derive_interpretation(selected_ai_metrics, minimum_rate)
    if level == "E4" and result.selected_ai_arm_ids:
        outcome_verdicts = [
            e4_outcome_verdict_by_arm.get(arm_id, False)
            for arm_id in result.selected_ai_arm_ids
        ]
        if not all(outcome_verdicts):
            result.derived_interpretation = "does-not-support-capability"
    if result.derived_interpretation is None:
        result.error("result interpretation cannot be derived from a qualifying AI arm")
    elif record["resultInterpretation"] != result.derived_interpretation:
        result.error(
            f"resultInterpretation {record['resultInterpretation']!r} contradicts qualifying-arm "
            f"outcomes; derived {result.derived_interpretation!r}"
        )

    return result


def discover_records(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.exists():
        return []
    return sorted(item for item in path.rglob("*.json") if item.is_file())


def build_summary(
    results: list[SemanticResult],
    as_of: datetime,
    validation_catalog: ValidationCatalog | dict[str, Any] | None = None,
    source_root: Path | None = None,
) -> dict[str, Any]:
    id_to_result = {
        result.record.get("recordId"): result
        for result in results
        if result.record.get("recordId")
    }
    superseded_ids: set[str] = set()
    for result in results:
        if result.errors:
            continue
        for old_id in result.record.get("supersedesRecordIds", []):
            old = id_to_result.get(old_id)
            if not old:
                result.error(f"supersedes unknown record {old_id!r}")
                continue
            if old.record.get("task", {}).get("slug") != result.record.get("task", {}).get("slug"):
                result.error(f"cannot supersede record {old_id!r} from another task")
                continue
            try:
                old_completed = parse_timestamp(old.record["trial"]["completedAt"])
                new_completed = parse_timestamp(result.record["trial"]["completedAt"])
            except (KeyError, TypeError, ValueError):
                result.error(f"cannot supersede malformed record {old_id!r}")
                continue
            if old_completed >= new_completed:
                result.error(f"superseding record must complete after {old_id!r}")
                continue
            superseded_ids.add(old_id)

    records = []
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        record = result.record
        record_id = record.get("recordId", "")
        claimed = record.get("claim", {}).get("evidenceLevel", "E0")
        stale = bool(result.stale_reasons)
        valid = not result.errors
        superseded = record_id in superseded_ids
        status = "invalid" if not valid else "superseded" if superseded else "stale" if stale else "active"
        item = {
            "recordId": record_id,
            "source": (
                os.path.relpath(result.source, source_root)
                if source_root and result.source.is_absolute()
                else str(result.source)
            ),
            "taskSlug": record.get("task", {}).get("slug", ""),
            "trialId": record.get("trial", {}).get("trialId", ""),
            "completedAt": record.get("trial", {}).get("completedAt", ""),
            "schemaVersion": result.schema_version,
            "policyVersion": result.policy_version,
            "claimedEvidenceLevel": claimed,
            "qualifiedEvidenceLevel": result.qualified_level,
            "resultInterpretation": result.derived_interpretation,
            "declaredResultInterpretation": record.get("resultInterpretation"),
            "qualifyingAiArmIds": result.qualifying_ai_arm_ids,
            "selectedAiArmIds": result.selected_ai_arm_ids,
            "selectedPublicArmIds": result.selected_public_arm_ids,
            "expiresAt": result.expires_at.isoformat() if result.expires_at else None,
            "status": status,
            "staleReasons": result.stale_reasons,
            "errors": result.errors,
            "warnings": result.warnings,
            "armMetrics": result.public_arm_metrics,
            "artifactVerification": result.artifact_verification,
        }
        records.append(item)
        if item["taskSlug"]:
            by_task[item["taskSlug"]].append(item)

    tasks: dict[str, Any] = {}
    for slug, task_records in sorted(by_task.items()):
        candidates = [item for item in task_records if item["status"] == "active"]
        candidates.sort(
            key=lambda item: (LEVELS.index(item["claimedEvidenceLevel"]), item["completedAt"]),
            reverse=True,
        )
        winner = candidates[0] if candidates else None
        tasks[slug] = {
            "effectiveEvidenceLevel": winner["claimedEvidenceLevel"] if winner else "E0",
            "effectiveRecordId": winner["recordId"] if winner else None,
            "schemaVersion": winner["schemaVersion"] if winner else None,
            "policyVersion": winner["policyVersion"] if winner else None,
            "resultInterpretation": winner["resultInterpretation"] if winner else None,
            "lastTestedAt": winner["completedAt"] if winner else None,
            "expiresAt": winner["expiresAt"] if winner else None,
            "armMetrics": winner["armMetrics"] if winner else [],
            "qualifyingAiArmIds": winner["qualifyingAiArmIds"] if winner else {},
            "selectedAiArmIds": winner["selectedAiArmIds"] if winner else [],
            "selectedPublicArmIds": winner["selectedPublicArmIds"] if winner else [],
            "recordCount": len(task_records),
            "activeRecordCount": len(candidates),
            "history": [item["recordId"] for item in sorted(task_records, key=lambda item: item["completedAt"])],
        }

    schema_versions = {
        result.schema_version for result in results if result.schema_version
    }
    policy_versions = {
        result.policy_version for result in results if result.policy_version
    }
    if isinstance(validation_catalog, ValidationCatalog):
        schema_versions.update(validation_catalog.schema_versions)
        policy_versions.update(validation_catalog.policy_versions)
    elif isinstance(validation_catalog, dict):
        # Compatibility for callers that have already resolved one exact policy.
        schema_versions.add(validation_catalog.get("schemaVersion"))
        policy_versions.add(validation_catalog.get("policyVersion"))
        schema_versions.discard(None)
        policy_versions.discard(None)

    version_key = lambda value: tuple(int(part) for part in value.split("."))
    return {
        "ledgerFormatVersion": "1.0",
        "schemaVersions": sorted(schema_versions, key=version_key),
        "policyVersions": sorted(policy_versions, key=version_key),
        "asOf": as_of.isoformat(),
        "stats": {
            "records": len(records),
            "active": sum(item["status"] == "active" for item in records),
            "stale": sum(item["status"] == "stale" for item in records),
            "superseded": sum(item["status"] == "superseded" for item in records),
            "invalid": sum(item["status"] == "invalid" for item in records),
            "tasksWithFreshEvidence": sum(task["effectiveEvidenceLevel"] != "E0" for task in tasks.values()),
        },
        "tasks": tasks,
        "records": records,
    }


def validate_all(
    record_paths: list[Path],
    validation_catalog: ValidationCatalog,
    task_catalog: dict[str, dict[str, Any]],
    repo_root: Path,
    as_of: datetime,
) -> list[SemanticResult]:
    results: list[SemanticResult] = []
    seen_record_ids: dict[str, Path] = {}
    seen_trial_ids: dict[str, Path] = {}
    for source in record_paths:
        try:
            record = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            result = SemanticResult(source, {})
            result.error(f"cannot read JSON: {exc}")
            results.append(result)
            continue
        try:
            schema, policy = validation_catalog.bundle_for(record)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            result = SemanticResult(source, record if isinstance(record, dict) else {})
            result.errors.extend(secret_scan_errors(record))
            result.error(f"cannot resolve immutable validation artifacts: {exc}")
            results.append(result)
            continue
        shape_errors = schema_errors(record, schema, schema)
        if shape_errors:
            result = SemanticResult(source, record if isinstance(record, dict) else {})
            result.errors.extend(secret_scan_errors(record))
            result.errors.extend(shape_errors)
            results.append(result)
            continue
        result = validate_semantics(source, record, policy, task_catalog, repo_root, as_of)
        record_id = record["recordId"]
        trial_id = record["trial"]["trialId"]
        if record_id in seen_record_ids:
            result.error(f"recordId duplicates {seen_record_ids[record_id]}")
        else:
            seen_record_ids[record_id] = source
        if trial_id in seen_trial_ids:
            result.error(f"trialId duplicates {seen_trial_ids[trial_id]}")
        else:
            seen_trial_ids[trial_id] = source
        results.append(result)
    return results


def resolve_cli_path(value: str, repo_root: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def task_evidence_view(summary: dict[str, Any], slug: str) -> dict[str, Any]:
    """Return the stable, public per-task portion of the validated overlay."""
    source = summary.get("tasks", {}).get(slug, {})
    return {
        "effectiveEvidenceLevel": source.get("effectiveEvidenceLevel", "E0"),
        "effectiveRecordId": source.get("effectiveRecordId"),
        "schemaVersion": source.get("schemaVersion"),
        "policyVersion": source.get("policyVersion"),
        "resultInterpretation": source.get("resultInterpretation"),
        "lastTestedAt": source.get("lastTestedAt"),
        "expiresAt": source.get("expiresAt"),
        "armMetrics": source.get("armMetrics", []),
        "qualifyingAiArmIds": source.get("qualifyingAiArmIds", {}),
        "selectedAiArmIds": source.get("selectedAiArmIds", []),
        "selectedPublicArmIds": source.get("selectedPublicArmIds", []),
        "recordCount": source.get("recordCount", 0),
        "activeRecordCount": source.get("activeRecordCount", 0),
        "history": source.get("history", []),
    }


def attach_summary_to_task_data(
    task_data: dict[str, Any], summary: dict[str, Any]
) -> dict[str, Any]:
    for category in task_data.get("categories", []):
        for task in category.get("tasks", []):
            task["evidence"] = task_evidence_view(summary, task.get("slug", ""))
    task_data["evidenceLedger"] = {
        "ledgerFormatVersion": summary["ledgerFormatVersion"],
        "schemaVersions": summary["schemaVersions"],
        "policyVersions": summary["policyVersions"],
        "stats": summary["stats"],
        "summaryUrl": "evidence-summary.json",
    }
    return task_data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--records", default="evidence/records")
    parser.add_argument("--schema-dir", default="evidence/schemas")
    parser.add_argument("--policy-dir", default="evidence/policies")
    parser.add_argument("--task-data", default="dashboard/data.json")
    parser.add_argument("--out", default="dashboard/evidence-summary.json")
    parser.add_argument("--as-of", help="ISO date or timezone-aware timestamp (default: now)")
    parser.add_argument("--strict-stale", action="store_true")
    parser.add_argument(
        "--attach-to-task-data",
        action="store_true",
        help="Attach the validated per-task overlay to --task-data after validation.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    try:
        as_of = parse_as_of(args.as_of)
        validation_catalog = ValidationCatalog(
            resolve_cli_path(args.schema_dir, repo_root),
            resolve_cli_path(args.policy_dir, repo_root),
        )
        validation_catalog.validate_catalog()
        task_catalog = load_task_catalog(resolve_cli_path(args.task_data, repo_root), repo_root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR setup: {exc}", file=sys.stderr)
        return 1

    record_paths = discover_records(resolve_cli_path(args.records, repo_root))
    results = validate_all(record_paths, validation_catalog, task_catalog, repo_root, as_of)
    summary = build_summary(results, as_of, validation_catalog, repo_root)
    out_path = resolve_cli_path(args.out, repo_root)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    if args.attach_to_task_data and not summary["stats"]["invalid"]:
        task_data_path = resolve_cli_path(args.task_data, repo_root)
        task_data = json.loads(task_data_path.read_text(encoding="utf-8"))
        attach_summary_to_task_data(task_data, summary)
        task_data_path.write_text(
            json.dumps(task_data, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )

    for result in results:
        relative = os.path.relpath(result.source, repo_root)
        for warning in result.warnings:
            print(f"WARN  {relative}: {warning}")
        for stale_reason in result.stale_reasons:
            print(f"STALE {relative}: {stale_reason}")
        for error in result.errors:
            print(f"ERROR {relative}: {error}")
    print(
        "evidence: "
        f"records={summary['stats']['records']}, active={summary['stats']['active']}, "
        f"stale={summary['stats']['stale']}, invalid={summary['stats']['invalid']} "
        f"-> {os.path.relpath(out_path, repo_root)}"
    )
    if summary["stats"]["invalid"]:
        return 1
    if args.strict_stale and summary["stats"]["stale"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
