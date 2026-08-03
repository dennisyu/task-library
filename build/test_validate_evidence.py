"""Regression tests for the E1-E4 evidence ledger and validator."""

from __future__ import annotations

import copy
import base64
import hashlib
import json
import sys
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


BUILD = Path(__file__).resolve().parent
ROOT = BUILD.parent
sys.path.insert(0, str(BUILD))

import validate_evidence as evidence  # noqa: E402


SLUG = "create-social-media-posts-per-platform"
SKILL_PATH = Path("skills/content-factory-process") / f"{SLUG}.md"
SCHEMA = json.loads((ROOT / "evidence/schemas/1.0.json").read_text(encoding="utf-8"))
POLICY = json.loads((ROOT / "evidence/policies/1.0.json").read_text(encoding="utf-8"))
TEST_PUBLIC_MODULUS = (
    "e4acb46159fde60e889da9d2beacab98e300196fce695fb24464d19aec84e0f2"
    "217c3b18e4520f6d24ad5ca396239c93c252af9d71b1515f75b46edc9f99f3fe"
    "d7df237c2704ce2ff2205a7d0d30eea063ad4a230bea848fea6ff8b7d0be4082b"
    "a6ad5edfd7f0cac01e119cfca291bbc1e1356af4228934119e53e693bdddbc5ce5"
    "6f6a9627fb6d804d12db47910786900fc2b57eac2ee0f7531ad27de7aa75f6e97"
    "30002cdb33fd2cbd43073bdde5ed61e64a1b5b836a108930274b2e23a3f909cde"
    "384a0798287f3f6cfa1797b2907edd7bded7cc246294e8465b9d6dc10fec9cc5d"
    "fdf51f2cc0c9839412e3513ad60bd6d6c8473561fa95a2faf0d3001b89"
)
TEST_POLICY = copy.deepcopy(POLICY)
TEST_POLICY["trustedReceiptIssuers"]["test-evidence-authority"] = {
    "algorithm": "rsa-pkcs1v15-sha256", "modulusHex": TEST_PUBLIC_MODULUS, "exponent": 65537
}
TEST_POLICY["trustedEvaluatorIssuers"]["evaluator-1"] = {
    "algorithm": "rsa-pkcs1v15-sha256", "modulusHex": TEST_PUBLIC_MODULUS, "exponent": 65537
}
TEST_POLICY["trustedProductionDataIssuers"]["test-production-data-authority"] = {
    "algorithm": "rsa-pkcs1v15-sha256", "modulusHex": TEST_PUBLIC_MODULUS, "exponent": 65537
}
TEST_POLICY["trustedOutcomeIssuers"]["test-outcome-authority"] = {
    "algorithm": "rsa-pkcs1v15-sha256", "modulusHex": TEST_PUBLIC_MODULUS, "exponent": 65537
}
CATALOG = evidence.ValidationCatalog(
    ROOT / "evidence/schemas", ROOT / "evidence/policies"
)
AS_OF = datetime(2026, 8, 2, 23, 59, 59, tzinfo=timezone.utc)
TASKS = {SLUG: {"slug": SLUG}}
TEST_RSA_D = int(
    "0f49504195bf784a8e6d63b5d7d339215e435a6ff3ef6d5b406130f5d74bc6b1"
    "c8f5420a16f13960c56be55e7621e94ca357ddaf7bb32bca62d6edf647a10603"
    "8a30bb7188363506557c3e304fda6e8940408c4d2d75bee8d3f62a3d37721063e"
    "ccc4982c04866f374a8b48e04689d170537abbac98466db9a3c8de0810502b4e5"
    "0aef6ca16be6f8a3d5601d0276f5e5e3a978ac663ee8d7f197fb0fed5d8b0ebb"
    "b6c3bf2313f79b83e1b3847a802cff364ae9b20f913826d876f9ac86fb588835"
    "21d1f5d18255bcdfb6f89c164d1864a25da3a07373975eb752e77c0a8b22d9d1"
    "fbfe43671427c5912818669e5e474539500b1fc78b590f48c3509db2074175",
    16,
)
TEST_RSA_N = int(TEST_PUBLIC_MODULUS, 16)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def rsa_sign(payload: bytes) -> str:
    width = (TEST_RSA_N.bit_length() + 7) // 8
    digest_info = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(payload).digest()
    padding = b"\xff" * (width - len(digest_info) - 3)
    encoded = b"\x00\x01" + padding + b"\x00" + digest_info
    signature = pow(int.from_bytes(encoded, "big"), TEST_RSA_D, TEST_RSA_N).to_bytes(width, "big")
    return base64.b64encode(signature).decode("ascii")


def forge_exponent_one_signature(payload: bytes, width: int = 256) -> str:
    """Reproduce the malformed-key regression without any private key."""
    digest_info = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(payload).digest()
    padding = b"\xff" * (width - len(digest_info) - 3)
    encoded = b"\x00\x01" + padding + b"\x00" + digest_info
    return base64.b64encode(encoded).decode("ascii")


def artifact(
    artifact_id: str,
    kind: str,
    *,
    sha256: str | None = None,
    uri: str | None = None,
    content: bytes | str | None = None,
) -> dict:
    raw = (
        content.encode("utf-8") if isinstance(content, str)
        else content if content is not None
        else artifact_id.encode("utf-8")
    )
    actual_sha = sha256 or hashlib.sha256(raw).hexdigest()
    actual_uri = uri or (
        "data:application/octet-stream;base64," + base64.b64encode(raw).decode("ascii")
    )
    return {
        "artifactId": artifact_id,
        "kind": kind,
        "uri": actual_uri,
        "sha256": actual_sha,
        "mediaType": "application/json",
        "access": "public",
        "containsSensitiveData": False,
        "redaction": "none-needed",
    }


def make_attempt(mode: str, case_id: str, index: int, day: int, accepted: bool = True) -> tuple[dict, dict]:
    output_id = f"output-{mode}-{index}"
    start = datetime(2026, 7, day, 8, 0, tzinfo=timezone.utc)
    end = start + timedelta(minutes=20)
    measurements = {
        "quality": 0.9 if accepted else 0.2,
        "endToEndScope": 0.8,
        "generalization": 0.8,
    }
    if mode in evidence.AI_MODES:
        measurements["autonomousShare"] = round(20 / 23 if mode == "ai-only" else 17 / 23, 6)
    labor = {
        "preparationMinutes": 1,
        "operatorMinutes": 10 if mode == "human-only" else 2 if mode == "human-ai" else 0,
        "supervisionMinutes": 1 if mode == "human-ai" else 0,
        "reviewMinutes": 2,
        "interventions": [],
    }
    attempt = {
        "attemptId": f"attempt-{mode}-{index}",
        "caseId": case_id,
        "startedAt": start.isoformat(),
        "completedAt": end.isoformat(),
        "status": "completed",
        "outputArtifactIds": [output_id],
        "acceptance": {
            "overall": "accepted" if accepted else "rejected",
            "judgedAt": (end + timedelta(minutes=5)).isoformat(),
            "evaluatorId": "evaluator-1",
            "criterionResults": [
                {
                    "criterionId": "criterion-1",
                    "result": "pass" if accepted else "fail",
                    "evidenceArtifactIds": [],
                }
            ],
        },
        "measurements": measurements,
        "labor": labor,
        "cost": {"currency": "USD", "amount": 0.05 if mode in evidence.AI_MODES else 0},
        "errors": [],
    }
    return attempt, artifact(output_id, "output")


def make_record(
    level: str = "E1",
    case_design: str = "known-demonstration",
    case_count: int = 1,
    modes: tuple[str, ...] = ("ai-only",),
    accepted: bool = True,
    spread_days: bool = False,
) -> dict:
    source_type = {
        "known-demonstration": "known",
        "repeated-cases": "known",
        "held-out": "held-out",
        "production": "production",
    }[case_design]
    trial_start = datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)
    trial_end = datetime(2026, 7, 30 if spread_days else 3, 23, 59, tzinfo=timezone.utc)
    artifacts = [
        artifact("context-1", "context"),
        artifact("model-release", "log"),
        artifact("orchestrator-release", "log"),
        artifact("tool-release", "log"),
    ]
    cases = []
    arms = []
    for index in range(1, case_count + 1):
        input_id = f"input-{index}"
        cases.append({
            "caseId": f"case-{index}",
            "sourceType": source_type,
            "inputArtifactIds": [input_id],
            "riskLevel": "R0",
        })
        if source_type == "held-out":
            cases[-1]["releasedAt"] = trial_start.isoformat()
            cases[-1]["contaminationCheck"] = "passed"
        artifacts.append(artifact(input_id, "input"))
    for mode in modes:
        attempts = []
        for index, case in enumerate(cases, start=1):
            if spread_days and case_count > 1:
                day = 1 + round((index - 1) * 29 / (case_count - 1))
            else:
                day = min(index, 3)
            attempt, output = make_attempt(mode, case["caseId"], index, day, accepted)
            attempts.append(attempt)
            artifacts.append(output)
        arm = {
            "armId": f"arm-{mode}",
            "mode": mode,
            "operatorIds": [] if mode == "ai-only" else [f"operator-{mode}"],
            "attempts": attempts,
        }
        if mode in evidence.AI_MODES:
            arm["stackId"] = "stack-1"
        arms.append(arm)

    record = {
        "$schema": SCHEMA["$id"],
        "schemaVersion": "1.0",
        "recordId": str(uuid.uuid4()),
        "recordedAt": (trial_end + timedelta(hours=1)).isoformat(),
        "recordedBy": {"id": "recorder-1", "role": "evaluation lead"},
        "task": {
            "slug": SLUG,
            "taskContractVersion": "1.0",
            "skill": {
                "uri": str(SKILL_PATH),
                "path": str(SKILL_PATH),
                "revision": "a" * 40,
                "sha256": evidence.sha256_file(ROOT / SKILL_PATH),
            },
        },
        "claim": {
            "evidenceLevel": level,
            "policyVersion": "1.0",
            "summary": "The recorded result is bounded to this task version and tested stack.",
        },
        "resultInterpretation": "supports-capability" if accepted else "does-not-support-capability",
        "trial": {
            "trialId": f"trial-{uuid.uuid4()}",
            "startedAt": trial_start.isoformat(),
            "completedAt": trial_end.isoformat(),
            "environment": "production" if case_design == "production" else "sandbox",
            "caseDesign": case_design,
            "cases": cases,
            "protocol": {
                "protocolId": "protocol-1",
                "version": "1.0",
                "preRegisteredAt": (
                    (trial_start - timedelta(days=1)).isoformat()
                    if case_design != "known-demonstration" else None
                ),
                "assignment": "paired" if len(modes) > 1 else "single-arm",
                "minimumWeightedScore": 1,
                "acceptanceCriteria": [
                    {
                        "criterionId": "criterion-1",
                        "description": "The complete artifact passes the task definition of done.",
                        "critical": True,
                        "weight": 1,
                    }
                ],
                "criticalFailures": [
                    {
                        "failureId": "unsafe-release",
                        "description": "An unapproved external mutation reached production.",
                        "severity": "S4",
                    }
                ],
                "evaluator": {
                    "id": "evaluator-1",
                    "independence": "peer" if len(modes) > 1 else "operator",
                    "blinded": len(modes) > 1,
                },
            },
        },
        "testedStacks": [
            {
                "stackId": "stack-1",
                "testedAt": trial_start.isoformat(),
                "model": {
                    "provider": "example-provider",
                    "modelId": "example-model",
                    "version": "2026-07-01",
                    "surface": "API",
                    "reasoningMode": "high",
                    "parameters": {"temperature": 0},
                    "immutableRelease": {
                        "kind": "artifact-digest",
                        "identifier": f"sha256:{digest('model-release')}",
                        "artifactId": "model-release",
                    },
                },
                "orchestrator": {
                    "name": "example-runner",
                    "version": "1.2.3",
                    "immutableRelease": {
                        "kind": "artifact-digest",
                        "identifier": f"sha256:{digest('orchestrator-release')}",
                        "artifactId": "orchestrator-release",
                    },
                },
                "tools": [
                    {
                        "name": "artifact-writer",
                        "version": "2.0.0",
                        "immutableRelease": {
                            "kind": "artifact-digest",
                            "identifier": f"sha256:{digest('tool-release')}",
                            "artifactId": "tool-release",
                        },
                        "accessMode": "draft",
                        "scopes": ["trial-output"],
                    }
                ],
                "memory": {"enabled": False, "description": "No cross-case memory."},
                "contextArtifactIds": ["context-1"],
                "permissions": [
                    {
                        "system": "trial-sandbox",
                        "level": "draft",
                        "scope": "isolated task artifacts",
                        "approvedBy": "owner-1",
                        "approvedAt": (trial_start - timedelta(days=1)).isoformat(),
                    }
                ],
            }
        ],
        "artifacts": artifacts,
        "arms": arms,
        "freshness": {
            "reviewDueAt": (trial_end + timedelta(days=60)).isoformat(),
            "materialChangeTriggers": list(POLICY["requiredMaterialChangeTriggers"]),
        },
        "supersedesRecordIds": [],
    }
    if {"human-only", "ai-only", "human-ai"}.issubset(set(modes)):
        record["trial"]["protocol"]["primaryComparison"] = {
            "humanOnlyArmId": "arm-human-only",
            "aiOnlyArmId": "arm-ai-only",
            "humanAiArmId": "arm-human-ai",
        }
    if case_design == "production":
        record["production"] = {
            "periodStart": "2026-07-01",
            "periodEnd": "2026-07-30",
            "deploymentId": "deployment-1",
            "accountableOwnerId": "owner-1",
            "samplingFrameArtifactId": "sampling-frame-1",
            "eventLedgerArtifactId": "production-event-ledger-1",
            "eventLedgerIssuerId": "test-production-data-authority",
            "incidents": [],
            "downstreamOutcomes": [
                {
                    "metric": "verified outcome achievement rate",
                    "unit": "ratio",
                    "value": 0.9 if accepted else 0.1,
                    "baseline": 0.5,
                    "direction": "increase",
                    "target": 0.7,
                    "armId": "arm-ai-only",
                    "stackId": "stack-1",
                    "attemptIds": [
                        attempt["attemptId"] for attempt in record["arms"][0]["attempts"]
                    ],
                    "periodStart": "2026-07-01",
                    "periodEnd": "2026-07-30",
                    "window": "2026-07-01/2026-07-30",
                    "outcomeIssuerId": "test-outcome-authority",
                    "evidenceArtifactIds": ["downstream-1"],
                }
            ],
        }
    if case_design == "known-demonstration":
        for arm in record["arms"]:
            for attempt in arm["attempts"]:
                attempt["measurements"].pop("generalization", None)
    if case_design != "known-demonstration":
        refresh_preregistration(record)
    else:
        refresh_attempt_receipts(record)
    return record


def add_arm(
    record: dict,
    arm_id: str,
    mode: str,
    *,
    accepted: bool,
    case_ids: list[str] | None = None,
    day: int | None = None,
) -> dict:
    selected_cases = case_ids or [case["caseId"] for case in record["trial"]["cases"]]
    attempts = []
    for offset, case_id in enumerate(selected_cases, start=1):
        attempt_day = day if day is not None else min(offset, 3)
        attempt, output = make_attempt(mode, case_id, 1000 + len(record["arms"]) * 100 + offset,
                                       attempt_day, accepted)
        attempts.append(attempt)
        record["artifacts"].append(output)
    arm = {
        "armId": arm_id,
        "mode": mode,
        "operatorIds": [] if mode == "ai-only" else [f"operator-{arm_id}"],
        "attempts": attempts,
    }
    if mode in evidence.AI_MODES:
        arm["stackId"] = "stack-1"
    record["arms"].append(arm)
    if record.get("production"):
        refresh_production_artifacts(record)
    else:
        refresh_attempt_receipts(record)
    return arm


def refresh_preregistration(record: dict) -> None:
    protocol = record["trial"]["protocol"]
    protocol_sha = evidence.protocol_binding_digest(record)
    protocol_bytes = evidence.canonical_json_bytes(evidence.protocol_binding_payload(record))
    preregistration = {
        "protocolArtifactId": "protocol-preregistration",
        "publishedAt": protocol["preRegisteredAt"],
        "protocolSha256": protocol_sha,
        "binding": {
            "kind": "signed-receipt",
            "immutableRef": "pending",
            "receiptArtifactId": "protocol-publication-receipt",
            "issuerId": "test-evidence-authority",
            "signature": "pending",
        },
    }
    receipt_bytes = evidence.canonical_json_bytes(
        evidence.preregistration_receipt_payload(record, preregistration)
    )
    receipt_sha = hashlib.sha256(receipt_bytes).hexdigest()
    preregistration["binding"]["immutableRef"] = f"sha256:{receipt_sha}"
    preregistration["binding"]["signature"] = rsa_sign(receipt_bytes)
    protocol["preregistration"] = preregistration
    upsert_artifact(record, artifact(
        "protocol-preregistration", "protocol", content=protocol_bytes
    ))
    upsert_artifact(record, artifact(
        "protocol-publication-receipt", "evaluation", content=receipt_bytes
    ))
    if record.get("production"):
        refresh_production_artifacts(record)
    else:
        refresh_attempt_receipts(record)


def upsert_artifact(record: dict, replacement: dict) -> None:
    for index, existing in enumerate(record["artifacts"]):
        if existing["artifactId"] == replacement["artifactId"]:
            record["artifacts"][index] = replacement
            return
    record["artifacts"].append(replacement)


def refresh_attempt_receipts(record: dict) -> None:
    pending: list[tuple[dict, dict, dict, str]] = []
    for arm in record["arms"]:
        for attempt in arm["attempts"]:
            for criterion in attempt["acceptance"]["criterionResults"]:
                receipt_id = f"receipt-{attempt['attemptId']}-{criterion['criterionId']}"
                prior_receipt_id = criterion.get("receiptArtifactId")
                auxiliary_ids = [
                    artifact_id
                    for artifact_id in criterion.get("evidenceArtifactIds", [])
                    if artifact_id not in {prior_receipt_id, receipt_id}
                ]
                criterion["receiptArtifactId"] = receipt_id
                criterion["receiptIssuerId"] = attempt["acceptance"].get("evaluatorId", "evaluator-1")
                criterion["evidenceArtifactIds"] = [receipt_id, *auxiliary_ids]
                pending.append((arm, attempt, criterion, receipt_id))
    # Every receipt artifact must exist before any canonical payload is made;
    # its URI/digest is intentionally omitted from that payload to break the
    # otherwise unavoidable receipt-hashes-itself cycle.
    for _, _, _, receipt_id in pending:
        upsert_artifact(record, artifact(receipt_id, "evaluation", content=b"pending"))
    for arm, attempt, criterion, receipt_id in pending:
        receipt_bytes = evidence.canonical_json_bytes(
            evidence.criterion_receipt_payload(record, arm["armId"], attempt, criterion)
        )
        criterion["receiptSignature"] = rsa_sign(receipt_bytes)
        upsert_artifact(record, artifact(receipt_id, "evaluation", content=receipt_bytes))


def refresh_production_artifacts(record: dict) -> None:
    production = record["production"]
    production.setdefault("eventLedgerIssuerId", "test-production-data-authority")
    for outcome in production["downstreamOutcomes"]:
        outcome.setdefault("outcomeIssuerId", "test-outcome-authority")
    sampling_bytes = evidence.canonical_json_bytes(evidence.sampling_frame_payload(record))
    event_bytes = evidence.canonical_json_bytes(evidence.production_event_ledger_payload(record))
    production["eventLedgerSignature"] = rsa_sign(event_bytes)
    upsert_artifact(record, artifact(
        production["samplingFrameArtifactId"], "protocol", content=sampling_bytes
    ))
    upsert_artifact(record, artifact(
        production["eventLedgerArtifactId"], "log", content=event_bytes
    ))
    for index, outcome in enumerate(production["downstreamOutcomes"], start=1):
        receipt_id = f"downstream-{index}"
        outcome["evidenceArtifactIds"] = [receipt_id]
        outcome_bytes = evidence.canonical_json_bytes(
            evidence.downstream_outcome_payload(record, outcome)
        )
        outcome["outcomeSignature"] = rsa_sign(outcome_bytes)
        upsert_artifact(record, artifact(receipt_id, "downstream", content=outcome_bytes))
    refresh_attempt_receipts(record)


def validate(record: dict, as_of: datetime = AS_OF) -> evidence.SemanticResult:
    shape = evidence.schema_errors(record, SCHEMA, SCHEMA)
    if shape:
        raise AssertionError("Fixture failed schema:\n" + "\n".join(shape))
    return evidence.validate_semantics(Path("fixture.json"), record, TEST_POLICY, TASKS, ROOT, as_of)


class EvidenceValidatorTests(unittest.TestCase):
    def test_rsa_verifier_rejects_unsafe_parameters_and_out_of_range_signature(self):
        payload = b"trust-key validation regression"
        valid_signature = rsa_sign(payload)
        self.assertTrue(evidence.verify_rsa_pkcs1v15_sha256(
            payload, valid_signature, TEST_PUBLIC_MODULUS, 65537
        ))
        self.assertFalse(evidence.verify_rsa_pkcs1v15_sha256(
            payload, forge_exponent_one_signature(payload), "ff" * 256, 1
        ))
        self.assertFalse(evidence.verify_rsa_pkcs1v15_sha256(
            payload, valid_signature, TEST_PUBLIC_MODULUS, 3
        ))
        self.assertFalse(evidence.verify_rsa_pkcs1v15_sha256(
            payload, valid_signature, "f" * 256, 65537
        ))
        modulus_width = (TEST_RSA_N.bit_length() + 7) // 8
        out_of_range = base64.b64encode(
            TEST_RSA_N.to_bytes(modulus_width, "big")
        ).decode("ascii")
        self.assertFalse(evidence.verify_rsa_pkcs1v15_sha256(
            payload, out_of_range, TEST_PUBLIC_MODULUS, 65537
        ))

    def test_policy_trust_key_metadata_is_validated_before_activation(self):
        malformed = copy.deepcopy(POLICY)
        malformed["trustedReceiptIssuers"]["unsafe"] = {
            "algorithm": "rsa-pkcs1v15-sha256",
            "modulusHex": "ff" * 256,
            "exponent": 1,
            "unexpected": True,
        }
        errors = evidence.policy_trust_key_errors(malformed)
        self.assertTrue(any("exponent must be 65537" in error for error in errors))
        self.assertTrue(any("unexpected fields" in error for error in errors))

    def test_exponent_one_forgery_cannot_promote_an_e4_record(self):
        record = make_record(
            level="E4", case_design="production", case_count=20,
            accepted=True, spread_days=True,
        )
        malicious_policy = copy.deepcopy(TEST_POLICY)
        for field in evidence.TRUST_MAP_FIELDS:
            malicious_policy[field] = {
                issuer_id: {
                    "algorithm": "rsa-pkcs1v15-sha256",
                    "modulusHex": "ff" * 256,
                    "exponent": 1,
                }
                for issuer_id in malicious_policy[field]
            }

        production = record["production"]
        event_payload = evidence.canonical_json_bytes(
            evidence.production_event_ledger_payload(record)
        )
        production["eventLedgerSignature"] = forge_exponent_one_signature(event_payload)
        for outcome in production["downstreamOutcomes"]:
            outcome_payload = evidence.canonical_json_bytes(
                evidence.downstream_outcome_payload(record, outcome)
            )
            outcome["outcomeSignature"] = forge_exponent_one_signature(outcome_payload)

        # Production signatures affect the record-wide evaluator payload. Rebuild
        # its byte receipts first, then replace only the excluded self-signatures.
        refresh_attempt_receipts(record)
        for arm in record["arms"]:
            for attempt in arm["attempts"]:
                for criterion in attempt["acceptance"]["criterionResults"]:
                    receipt_payload = evidence.canonical_json_bytes(
                        evidence.criterion_receipt_payload(
                            record, arm["armId"], attempt, criterion
                        )
                    )
                    criterion["receiptSignature"] = forge_exponent_one_signature(
                        receipt_payload
                    )

        preregistration = record["trial"]["protocol"]["preregistration"]
        prereg_payload = evidence.canonical_json_bytes(
            evidence.preregistration_receipt_payload(record, preregistration)
        )
        preregistration["binding"]["signature"] = forge_exponent_one_signature(
            prereg_payload
        )

        result = evidence.validate_semantics(
            Path("fixture.json"), record, malicious_policy, TASKS, ROOT, AS_OF
        )
        self.assertNotIn("E4", result.qualified_levels)
        self.assertTrue(any(
            "policy trust configuration" in error and "exponent must be 65537" in error
            for error in result.errors
        ))

    def test_shipped_policy_has_no_unreviewed_trust_anchors(self):
        self.assertEqual(POLICY["trustedReceiptIssuers"], {})
        self.assertEqual(POLICY["trustedEvaluatorIssuers"], {})
        self.assertEqual(POLICY["trustedProductionDataIssuers"], {})
        self.assertEqual(POLICY["trustedOutcomeIssuers"], {})
        record = make_record(level="E2", case_design="held-out", case_count=3)
        result = evidence.validate_semantics(
            Path("fixture.json"), record, POLICY, TASKS, ROOT, AS_OF
        )
        self.assertEqual(result.qualified_level, "E0")
        self.assertTrue(any("trusted" in error for error in result.errors))

    def test_e1_demo_qualifies_without_claiming_generalization_tci(self):
        result = validate(make_record())
        self.assertEqual(result.errors, [])
        self.assertEqual(result.qualified_level, "E1")
        self.assertIsNone(result.arm_metrics[0]["taskCapabilityIndex"])
        self.assertEqual(result.arm_metrics[0]["acceptanceRate"], 1)

    def test_e2_negative_trial_is_valid_rigorous_evidence(self):
        record = make_record(
            level="E2", case_design="held-out", case_count=3, accepted=False
        )
        result = validate(record)
        self.assertEqual(result.errors, [])
        self.assertIn("E2", result.qualified_levels)
        self.assertNotIn("E1", result.qualified_levels)
        self.assertEqual(result.arm_metrics[0]["acceptanceRate"], 0)
        self.assertEqual(result.arm_metrics[0]["taskCapabilityIndex"], 0)

    def test_e2_overclaim_on_single_known_case_fails(self):
        record = make_record(level="E2")
        result = validate(record)
        self.assertTrue(any("E2 evidence overclaim" in error for error in result.errors))
        self.assertEqual(result.qualified_level, "E1")

    def test_e3_requires_and_accepts_matched_three_arm_comparison(self):
        record = make_record(
            level="E3",
            case_design="held-out",
            case_count=3,
            modes=("human-only", "ai-only", "human-ai"),
        )
        result = validate(record)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.qualified_level, "E3")
        self.assertEqual(
            {metric["mode"] for metric in result.arm_metrics},
            {"human-only", "ai-only", "human-ai"},
        )

    def test_held_out_release_integrity_and_e3_blinding_are_enforced(self):
        record = make_record(
            level="E3",
            case_design="held-out",
            case_count=3,
            modes=("human-only", "ai-only", "human-ai"),
        )
        del record["trial"]["cases"][0]["releasedAt"]
        record["trial"]["protocol"]["evaluator"]["blinded"] = False
        result = validate(record)
        self.assertTrue(any("needs releasedAt" in error for error in result.errors))
        self.assertTrue(any("evaluator is not blinded" in error for error in result.errors))

    def test_e3_ai_arms_must_use_the_same_tested_stack(self):
        record = make_record(
            level="E3",
            case_design="held-out",
            case_count=3,
            modes=("human-only", "ai-only", "human-ai"),
        )
        second_stack = copy.deepcopy(record["testedStacks"][0])
        second_stack["stackId"] = "stack-2"
        record["testedStacks"].append(second_stack)
        next(arm for arm in record["arms"] if arm["mode"] == "human-ai")["stackId"] = "stack-2"
        result = validate(record)
        self.assertTrue(any("do not share a tested stack" in error for error in result.errors))

    def test_e4_requires_sustained_case_level_production_span(self):
        record = make_record(
            level="E4",
            case_design="production",
            case_count=20,
            accepted=True,
            spread_days=True,
        )
        result = validate(record)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.qualified_level, "E4")

        compressed = copy.deepcopy(record)
        for attempt in compressed["arms"][0]["attempts"]:
            attempt["startedAt"] = "2026-07-01T08:00:00+00:00"
            attempt["completedAt"] = "2026-07-01T08:20:00+00:00"
            attempt["acceptance"]["judgedAt"] = "2026-07-01T08:25:00+00:00"
        compressed_result = validate(compressed)
        self.assertTrue(any("no single production AI-containing arm" in error
                            for error in compressed_result.errors))

    def test_e4_post_release_error_must_link_to_incident_ledger(self):
        record = make_record(
            level="E4",
            case_design="production",
            case_count=20,
            accepted=True,
            spread_days=True,
        )
        attempt = record["arms"][0]["attempts"][0]
        attempt["errors"].append({
            "errorId": "error-1",
            "severity": "S2",
            "detectedStage": "post-release",
            "detectedBy": "customer",
            "description": "The published artifact used an outdated destination link.",
            "evidenceArtifactIds": attempt["outputArtifactIds"],
            "recovery": {
                "attempted": True,
                "successful": True,
                "minutes": 4,
                "action": "Corrected and rechecked the destination.",
                "artifactIds": attempt["outputArtifactIds"],
            },
        })
        result = validate(record)
        self.assertTrue(any("needs incidentId" in error for error in result.errors))

    def test_acceptance_label_must_match_critical_weighted_result(self):
        record = make_record()
        record["arms"][0]["attempts"][0]["acceptance"]["criterionResults"][0]["result"] = "fail"
        result = validate(record)
        self.assertTrue(any("overall acceptance disagrees" in error for error in result.errors))

    def test_ai_only_active_human_intervention_must_be_human_ai(self):
        record = make_record()
        record["arms"][0]["attempts"][0]["labor"]["supervisionMinutes"] = 2
        result = validate(record)
        self.assertTrue(any("AI-only but contains active human work" in error for error in result.errors))

    def test_expired_or_changed_skill_is_stale_and_effective_level_is_e0(self):
        record = make_record()
        record["freshness"]["reviewDueAt"] = "2026-07-15T00:00:00+00:00"
        refresh_attempt_receipts(record)
        result = validate(record)
        self.assertEqual(result.errors, [])
        self.assertTrue(result.stale_reasons)
        summary = evidence.build_summary([result], AS_OF, POLICY)
        self.assertEqual(summary["tasks"][SLUG]["effectiveEvidenceLevel"], "E0")

        changed = make_record()
        changed["task"]["skill"]["sha256"] = "0" * 64
        changed_result = validate(changed)
        self.assertTrue(any("SHA-256 differs" in reason for reason in changed_result.stale_reasons))

    def test_duplicate_record_and_trial_ids_fail_across_files(self):
        first = make_record()
        second = copy.deepcopy(first)
        with tempfile.TemporaryDirectory() as directory:
            first_path = Path(directory) / "first.json"
            second_path = Path(directory) / "second.json"
            first_path.write_text(json.dumps(first), encoding="utf-8")
            second_path.write_text(json.dumps(second), encoding="utf-8")
            results = evidence.validate_all(
                [first_path, second_path], CATALOG, TASKS, ROOT, AS_OF
            )
        self.assertTrue(any("recordId duplicates" in error for error in results[1].errors))
        self.assertTrue(any("trialId duplicates" in error for error in results[1].errors))

    def test_invalid_correction_cannot_supersede_valid_evidence(self):
        first_record = make_record()
        first = validate(first_record)
        correction_record = make_record()
        correction_record["supersedesRecordIds"] = [first_record["recordId"]]
        correction_record["arms"][0]["attempts"][0]["acceptance"]["criterionResults"][0]["result"] = "fail"
        correction = validate(correction_record)
        summary = evidence.build_summary([first, correction], AS_OF, POLICY)
        first_summary = next(
            item for item in summary["records"] if item["recordId"] == first_record["recordId"]
        )
        self.assertEqual(first_summary["status"], "active")

    def test_schema_rejects_moving_model_alias(self):
        record = make_record()
        record["testedStacks"][0]["model"]["version"] = "latest"
        result = validate(record)
        self.assertTrue(any("moving model version" in error for error in result.errors))

    def test_non_finite_measurements_are_rejected(self):
        record = make_record(level="E2", case_design="repeated-cases", case_count=3)
        record["arms"][0]["attempts"][0]["measurements"]["quality"] = float("nan")
        errors = evidence.schema_errors(record, SCHEMA, SCHEMA)
        self.assertTrue(any("number must be finite" in error for error in errors))

    def test_distinct_case_ids_must_have_distinct_input_digests(self):
        record = make_record(level="E2", case_design="repeated-cases", case_count=3)
        record["trial"]["cases"][1]["inputArtifactIds"] = list(
            record["trial"]["cases"][0]["inputArtifactIds"]
        )
        result = validate(record)
        self.assertTrue(any("identical input artifact digests" in error for error in result.errors))

    def test_aborted_runs_reduce_reliability_and_cannot_be_cherry_picked(self):
        record = make_record(level="E2", case_design="repeated-cases", case_count=3)
        arm = record["arms"][0]
        for index in range(30):
            attempt = copy.deepcopy(arm["attempts"][index % 3])
            attempt["attemptId"] = f"aborted-{index}"
            attempt["status"] = "aborted"
            attempt["outputArtifactIds"] = []
            attempt["acceptance"] = {"overall": "not-evaluated", "criterionResults": []}
            attempt.pop("measurements", None)
            arm["attempts"].append(attempt)
        result = validate(record)
        self.assertEqual(result.arm_metrics[0]["acceptanceRate"], round(3 / 33, 4))
        self.assertEqual(result.arm_metrics[0]["abortedAttempts"], 30)
        self.assertTrue(any("allowed attempt counts" in error for error in result.errors))
        self.assertTrue(any("cannot be derived from a qualifying AI arm" in error
                            for error in result.errors))

    def test_acceptance_policy_rejects_zero_threshold_and_no_critical_criterion(self):
        record = make_record()
        record["trial"]["protocol"]["minimumWeightedScore"] = 0
        shape_errors = evidence.schema_errors(record, SCHEMA, SCHEMA)
        self.assertTrue(any("must be >= 0.7" in error for error in shape_errors))

        record = make_record()
        record["trial"]["protocol"]["acceptanceCriteria"][0]["critical"] = False
        attempt = record["arms"][0]["attempts"][0]
        attempt["acceptance"]["criterionResults"][0]["result"] = "fail"
        result = validate(record)
        self.assertTrue(any("at least one critical" in error for error in result.errors))
        self.assertTrue(any("overall acceptance disagrees" in error for error in result.errors))

    def test_s4_error_forces_rejection_and_requires_critical_failure_link(self):
        record = make_record()
        attempt = record["arms"][0]["attempts"][0]
        attempt["errors"].append({
            "errorId": "s4-error",
            "severity": "S4",
            "detectedStage": "pre-release",
            "detectedBy": "human",
            "description": "A critical policy violation was detected before release.",
            "evidenceArtifactIds": attempt["outputArtifactIds"],
            "recovery": {
                "attempted": False,
                "successful": None,
                "minutes": 0,
                "action": "",
                "artifactIds": [],
            },
        })
        result = validate(record)
        self.assertTrue(any("S4 error must reference" in error for error in result.errors))
        self.assertTrue(any("overall acceptance disagrees" in error for error in result.errors))

    def test_e3_rejects_unmatched_extra_ai_cases(self):
        record = make_record(
            level="E3",
            case_design="held-out",
            case_count=3,
            modes=("human-only", "ai-only", "human-ai"),
        )
        extra_input = artifact("input-extra", "input")
        record["artifacts"].append(extra_input)
        record["trial"]["cases"].append({
            "caseId": "case-extra",
            "sourceType": "held-out",
            "inputArtifactIds": ["input-extra"],
            "riskLevel": "R0",
            "releasedAt": record["trial"]["startedAt"],
            "contaminationCheck": "passed",
        })
        attempt, output = make_attempt("ai-only", "case-extra", 99, 3, True)
        record["arms"][1]["attempts"].append(attempt)
        record["artifacts"].append(output)
        refresh_attempt_receipts(record)
        result = validate(record)
        self.assertTrue(any("identical evaluated case sets" in error or "cover every" in error
                            for error in result.errors))

    def test_current_built_skill_digest_is_checked_without_local_path(self):
        record = make_record()
        del record["task"]["skill"]["path"]
        record["task"]["skill"]["sha256"] = "0" * 64
        catalog = {SLUG: {"slug": SLUG, "content": (ROOT / SKILL_PATH).read_text(encoding="utf-8")}}
        result = evidence.validate_semantics(
            Path("fixture.json"), record, TEST_POLICY, catalog, ROOT, AS_OF
        )
        self.assertTrue(any("current built skill SHA-256" in reason for reason in result.stale_reasons))

    def test_trailing_newline_source_digest_does_not_stale_a_valid_record(self):
        source_text = (ROOT / SKILL_PATH).read_text(encoding="utf-8")
        self.assertTrue(source_text.endswith("\n"), "fixture must exercise terminal-newline normalization")
        record = make_record()
        catalog = {
            SLUG: {
                "slug": SLUG,
                "content": source_text.strip(),
                "sourceSha256": digest(source_text),
            }
        }
        result = evidence.validate_semantics(
            Path("fixture.json"), record, TEST_POLICY, catalog, ROOT, AS_OF
        )
        self.assertEqual(result.errors, [])
        self.assertEqual(result.stale_reasons, [])
        self.assertFalse(any("legacy content digest" in warning for warning in result.warnings))

    def test_pathless_legacy_digest_fallback_is_deterministic_and_fail_closed(self):
        legacy_content = (ROOT / SKILL_PATH).read_text(encoding="utf-8").strip()
        record = make_record()
        del record["task"]["skill"]["path"]
        record["task"]["skill"]["sha256"] = digest(legacy_content)
        refresh_attempt_receipts(record)
        catalog = {SLUG: {"slug": SLUG, "content": legacy_content}}
        first = evidence.validate_semantics(
            Path("fixture.json"), record, TEST_POLICY, catalog, ROOT, AS_OF
        )
        second = evidence.validate_semantics(
            Path("fixture.json"), copy.deepcopy(record), TEST_POLICY, copy.deepcopy(catalog), ROOT, AS_OF
        )
        self.assertEqual(first.errors, second.errors)
        self.assertEqual(first.warnings, second.warnings)
        self.assertEqual(first.stale_reasons, second.stale_reasons)
        self.assertEqual(first.errors, [])
        self.assertEqual(first.stale_reasons, [])
        self.assertTrue(any("deterministic legacy content digest" in warning
                            for warning in first.warnings))

        uncheckable = evidence.validate_semantics(
            Path("fixture.json"), record, TEST_POLICY, {SLUG: {"slug": SLUG}}, ROOT, AS_OF
        )
        self.assertTrue(any("pathless task skill digest cannot be checked" in error
                            for error in uncheckable.errors))

        explicitly_unavailable = evidence.validate_semantics(
            Path("fixture.json"),
            record,
            TEST_POLICY,
            {SLUG: {"slug": SLUG, "content": legacy_content, "sourceSha256": None}},
            ROOT,
            AS_OF,
        )
        self.assertTrue(any("sourceSha256 unavailable" in error
                            for error in explicitly_unavailable.errors))
        self.assertFalse(any("legacy content digest" in warning
                             for warning in explicitly_unavailable.warnings))

    def test_temporal_provenance_is_ordered(self):
        record = make_record()
        attempt = record["arms"][0]["attempts"][0]
        attempt["acceptance"]["judgedAt"] = "2025-01-01T00:00:00+00:00"
        record["testedStacks"][0]["testedAt"] = "2027-01-01T00:00:00+00:00"
        record["testedStacks"][0]["permissions"][0]["approvedAt"] = "2027-01-01T00:00:00+00:00"
        result = validate(record)
        self.assertTrue(any("judged before" in error for error in result.errors))
        self.assertTrue(any("tested after" in error or "testedAt is in the future" in error
                            for error in result.errors))
        self.assertTrue(any("permission" in error and "after" in error for error in result.errors))

    def test_supports_capability_label_must_match_observed_outcomes(self):
        record = make_record(
            level="E2", case_design="held-out", case_count=3, accepted=False
        )
        record["resultInterpretation"] = "supports-capability"
        refresh_attempt_receipts(record)
        result = validate(record)
        self.assertTrue(any("contradicts qualifying-arm outcomes" in error for error in result.errors))

    def test_validated_summary_attaches_as_a_distinct_task_evidence_field(self):
        result = validate(make_record())
        summary = evidence.build_summary([result], AS_OF, POLICY)
        task_data = {"categories": [{"tasks": [{"slug": SLUG}, {"slug": "unseen-task"}]}]}
        attached = evidence.attach_summary_to_task_data(task_data, summary)
        first, unseen = attached["categories"][0]["tasks"]
        self.assertEqual(first["evidence"]["effectiveEvidenceLevel"], "E1")
        self.assertEqual(unseen["evidence"]["effectiveEvidenceLevel"], "E0")
        self.assertEqual(attached["evidenceLedger"]["policyVersions"], ["1.0"])

    def test_e2_interpretation_ignores_unqualified_one_case_arm(self):
        record = make_record(
            level="E2", case_design="held-out", case_count=3, accepted=False
        )
        extra = add_arm(record, "arm-ai-only-extra", "ai-only", accepted=True,
                        case_ids=["case-1"])
        extra["attempts"][0]["cost"]["amount"] = 999
        refresh_preregistration(record)
        result = validate(record)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.qualifying_ai_arm_ids["E2"], ["arm-ai-only"])
        self.assertEqual(result.selected_ai_arm_ids, ["arm-ai-only"])
        self.assertEqual(result.derived_interpretation, "does-not-support-capability")
        self.assertEqual([item["armId"] for item in result.public_arm_metrics],
                         ["arm-ai-only"])
        self.assertEqual(result.public_arm_metrics[0]["costUsd"], 0.15)

    def test_e3_unqualified_extra_arm_cannot_influence_public_result(self):
        record = make_record(
            level="E3", case_design="held-out", case_count=3,
            modes=("human-only", "ai-only", "human-ai"),
        )
        add_arm(record, "arm-ai-only-extra", "ai-only", accepted=False,
                case_ids=["case-1"])
        refresh_preregistration(record)
        result = validate(record)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.derived_interpretation, "supports-capability")
        self.assertEqual(
            set(result.selected_public_arm_ids),
            {"arm-human-only", "arm-ai-only", "arm-human-ai"},
        )
        self.assertNotIn("arm-ai-only-extra", {
            metric["armId"] for metric in result.public_arm_metrics
        })

    def test_e3_uses_preregistered_primary_comparison_when_multiple_qualify(self):
        record = make_record(
            level="E3", case_design="held-out", case_count=3,
            modes=("human-only", "ai-only", "human-ai"),
        )
        add_arm(record, "arm-ai-only-adverse", "ai-only", accepted=False)
        add_arm(record, "arm-human-ai-adverse", "human-ai", accepted=False)
        refresh_preregistration(record)
        result = validate(record)
        self.assertEqual(result.errors, [])
        self.assertIn("arm-ai-only-adverse", result.qualifying_ai_arm_ids["E3"])
        self.assertEqual(result.selected_ai_arm_ids, ["arm-ai-only", "arm-human-ai"])
        self.assertEqual(result.derived_interpretation, "supports-capability")
        self.assertNotIn("arm-ai-only-adverse", result.selected_public_arm_ids)

    def test_e4_span_cannot_be_assembled_across_unqualified_arms(self):
        record = make_record(
            level="E4", case_design="production", case_count=20,
            accepted=True, spread_days=True,
        )
        for attempt in record["arms"][0]["attempts"]:
            attempt["startedAt"] = "2026-07-01T08:00:00+00:00"
            attempt["completedAt"] = "2026-07-01T08:20:00+00:00"
            attempt["acceptance"]["judgedAt"] = "2026-07-01T08:25:00+00:00"
        add_arm(record, "arm-ai-only-late", "ai-only", accepted=True,
                case_ids=["case-1"], day=30)
        refresh_preregistration(record)
        result = validate(record)
        self.assertEqual(result.qualifying_ai_arm_ids["E4"], [])
        self.assertTrue(any("no single production AI-containing arm" in error
                            for error in result.errors))

    def test_e3_evaluator_id_must_be_disjoint_from_all_participant_roles(self):
        record = make_record(
            level="E3", case_design="held-out", case_count=3,
            modes=("human-only", "ai-only", "human-ai"),
        )
        record["trial"]["protocol"]["evaluator"]["id"] = "operator-human-only"
        for arm in record["arms"]:
            for attempt in arm["attempts"]:
                attempt["acceptance"]["evaluatorId"] = "operator-human-only"
        refresh_preregistration(record)
        result = validate(record)
        self.assertTrue(any("independence label conflicts" in error for error in result.errors))
        self.assertTrue(any("evaluator ID is not independent" in error for error in result.errors))

    def test_e3_requires_trusted_evaluator_signed_acceptance_receipts(self):
        record = make_record(
            level="E3", case_design="held-out", case_count=3,
            modes=("human-only", "ai-only", "human-ai"),
        )
        criterion = record["arms"][1]["attempts"][0]["acceptance"]["criterionResults"][0]
        criterion["receiptSignature"] = base64.b64encode(b"0" * 128).decode("ascii")
        result = validate(record)
        self.assertNotIn("E3", result.qualified_levels)
        self.assertTrue(any("trusted evaluator signature" in error for error in result.errors))

    def test_evaluator_signature_binds_every_result_affecting_record_section(self):
        record = make_record()
        arm = record["arms"][0]
        attempt = arm["attempts"][0]
        criterion = attempt["acceptance"]["criterionResults"][0]
        original_signature = criterion["receiptSignature"]

        mutations = {
            "schema URI": (("$schema",), "https://example.invalid/changed-schema.json"),
            "schema version": (("schemaVersion",), "1.1"),
            "record identity": (("recordId",), str(uuid.uuid4())),
            "record time": (("recordedAt",), "2026-07-04T01:00:00+00:00"),
            "recorder": (("recordedBy", "role"), "independent evaluation lead"),
            "claimed level": (("claim", "evidenceLevel"), "E2"),
            "policy identity": (("claim", "policyVersion"), "2.0"),
            "claim": (("claim", "summary"), "A materially different bounded evidence claim."),
            "interpretation": (("resultInterpretation",), "mixed"),
            "freshness": (("freshness", "reviewDueAt"), "2026-08-31T23:59:00+00:00"),
            "freshness triggers": (("freshness", "materialChangeTriggers"), ["environment"]),
            "supersession": (("supersedesRecordIds",), [str(uuid.uuid4())]),
            "record notes": (("notes",), "A result-affecting qualification note."),
            "task slug": (("task", "slug"), "changed-task-slug"),
            "task contract": (("task", "taskContractVersion"), "1.1"),
            "skill URI": (("task", "skill", "uri"), "skills/changed.md"),
            "skill revision": (("task", "skill", "revision"), "b" * 40),
            "skill digest": (("task", "skill", "sha256"), "b" * 64),
            "trial identity": (("trial", "trialId"), "trial-mutated"),
            "trial window": (("trial", "startedAt"), "2026-06-30T23:00:00+00:00"),
            "trial completion": (("trial", "completedAt"), "2026-07-03T23:58:00+00:00"),
            "environment": (("trial", "environment"), "staging"),
            "case design": (("trial", "caseDesign"), "repeated-cases"),
            "case metadata": (("trial", "cases", 0, "riskLevel"), "R1"),
            "protocol identity": (("trial", "protocol", "protocolId"), "protocol-mutated"),
            "protocol version": (("trial", "protocol", "version"), "1.1"),
            "preregistration time": (
                ("trial", "protocol", "preRegisteredAt"),
                "2026-06-30T00:00:00+00:00",
            ),
            "assignment": (("trial", "protocol", "assignment"), "paired"),
            "protocol threshold": (("trial", "protocol", "minimumWeightedScore"), 0.9),
            "criterion rubric": (
                ("trial", "protocol", "acceptanceCriteria", 0, "description"),
                "A changed definition of done that still has valid schema shape.",
            ),
            "evaluator arrangement": (
                ("trial", "protocol", "evaluator", "notes"),
                "A changed evaluation arrangement.",
            ),
            "critical failure rubric": (
                ("trial", "protocol", "criticalFailures", 0, "description"),
                "A changed critical failure definition.",
            ),
            "arm identity": (("arms", 0, "armId"), "arm-mutated"),
            "arm mode": (("arms", 0, "mode"), "human-ai"),
            "arm stack": (("arms", 0, "stackId"), "stack-mutated"),
            "arm operators": (("arms", 0, "operatorIds"), ["operator-added-after-run"]),
            "stack identity": (("testedStacks", 0, "stackId"), "stack-mutated"),
            "stack test time": (("testedStacks", 0, "testedAt"), "2026-06-30T23:59:00+00:00"),
            "stack model": (("testedStacks", 0, "model", "version"), "2026-07-02"),
            "stack orchestrator": (("testedStacks", 0, "orchestrator", "version"), "1.2.4"),
            "stack tool": (("testedStacks", 0, "tools", 0, "scopes"), ["changed-scope"]),
            "stack memory": (
                ("testedStacks", 0, "memory", "description"),
                "A different memory configuration.",
            ),
            "stack permission": (
                ("testedStacks", 0, "permissions", 0, "scope"),
                "changed artifact scope",
            ),
            "attempt timing": (("arms", 0, "attempts", 0, "startedAt"), "2026-07-01T08:01:00+00:00"),
            "attempt identity": (("arms", 0, "attempts", 0, "attemptId"), "attempt-mutated"),
            "attempt case": (("arms", 0, "attempts", 0, "caseId"), "case-mutated"),
            "attempt status": (("arms", 0, "attempts", 0, "status"), "aborted"),
            "attempt outputs": (("arms", 0, "attempts", 0, "outputArtifactIds"), []),
            "attempt measurements": (("arms", 0, "attempts", 0, "measurements", "quality"), 0.8),
            "attempt labor": (("arms", 0, "attempts", 0, "labor", "reviewMinutes"), 3),
            "attempt cost": (("arms", 0, "attempts", 0, "cost", "amount"), 0.06),
            "attempt notes": (("arms", 0, "attempts", 0, "notes"), "Changed run note."),
            "attempt errors and recovery": (("arms", 0, "attempts", 0, "errors"), [{
                "errorId": "changed-error",
                "severity": "S1",
                "detectedStage": "pre-release",
                "detectedBy": "human",
                "description": "A changed result-affecting error record.",
                "evidenceArtifactIds": ["output-ai-only-1"],
                "recovery": {
                    "attempted": True,
                    "successful": True,
                    "minutes": 1,
                    "action": "Rechecked the output.",
                    "artifactIds": ["output-ai-only-1"],
                },
            }]),
            "acceptance": (("arms", 0, "attempts", 0, "acceptance", "overall"), "rejected"),
            "evaluator identity": (
                ("arms", 0, "attempts", 0, "acceptance", "evaluatorId"),
                "evaluator-mutated",
            ),
            "judgment time": (
                ("arms", 0, "attempts", 0, "acceptance", "judgedAt"),
                "2026-07-01T08:26:00+00:00",
            ),
            "criterion result": (
                ("arms", 0, "attempts", 0, "acceptance", "criterionResults", 0, "result"),
                "fail",
            ),
            "criterion receipt identity": (
                ("arms", 0, "attempts", 0, "acceptance", "criterionResults", 0,
                 "receiptArtifactId"),
                "receipt-mutated",
            ),
            "criterion issuer identity": (
                ("arms", 0, "attempts", 0, "acceptance", "criterionResults", 0,
                 "receiptIssuerId"),
                "evaluator-mutated",
            ),
            "criterion evidence references": (
                ("arms", 0, "attempts", 0, "acceptance", "criterionResults", 0,
                 "evidenceArtifactIds"),
                [criterion["receiptArtifactId"], "output-ai-only-1"],
            ),
        }

        for label, (path, replacement) in mutations.items():
            with self.subTest(section=label):
                changed = copy.deepcopy(record)
                target = changed
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = replacement
                changed_arm = changed["arms"][0]
                changed_attempt = changed_arm["attempts"][0]
                changed_criterion = changed_attempt["acceptance"]["criterionResults"][0]
                changed_payload = evidence.canonical_json_bytes(
                    evidence.criterion_receipt_payload(
                        changed, changed_arm["armId"], changed_attempt, changed_criterion
                    )
                )
                self.assertFalse(
                    evidence.verify_rsa_pkcs1v15_sha256(
                        changed_payload,
                        original_signature,
                        TEST_PUBLIC_MODULUS,
                        65537,
                    ),
                    label,
                )

    def test_evaluator_binding_exclusions_are_path_specific(self):
        record = make_record()
        receipt_id = record["arms"][0]["attempts"][0]["acceptance"][
            "criterionResults"
        ][0]["receiptArtifactId"]
        parameters = record["testedStacks"][0]["model"]["parameters"]
        parameters["receiptSignature"] = "before"
        parameters["artifactShapedParameter"] = {
            "artifactId": receipt_id,
            "uri": "before",
            "sha256": "a" * 64,
        }
        refresh_attempt_receipts(record)

        parameters["receiptSignature"] = "after"
        parameters["artifactShapedParameter"]["uri"] = "after"
        parameters["artifactShapedParameter"]["sha256"] = "b" * 64
        result = validate(record)
        self.assertEqual(result.qualifying_ai_arm_ids["E1"], [])
        self.assertTrue(any("trusted evaluator signature" in error for error in result.errors))

    def test_preregistration_receipt_is_bound_to_record_trial_task_and_protocol_identity(self):
        record = make_record(level="E2", case_design="held-out", case_count=3)
        preregistration = record["trial"]["protocol"]["preregistration"]
        original_payload = evidence.canonical_json_bytes(
            evidence.preregistration_receipt_payload(record, preregistration)
        )
        self.assertTrue(evidence.verify_rsa_pkcs1v15_sha256(
            original_payload,
            preregistration["binding"]["signature"],
            TEST_PUBLIC_MODULUS,
            65537,
        ))

        record["recordId"] = str(uuid.uuid4())
        changed_payload = evidence.canonical_json_bytes(
            evidence.preregistration_receipt_payload(record, preregistration)
        )
        self.assertFalse(evidence.verify_rsa_pkcs1v15_sha256(
            changed_payload,
            preregistration["binding"]["signature"],
            TEST_PUBLIC_MODULUS,
            65537,
        ))
        refresh_attempt_receipts(record)
        result = validate(record)
        self.assertNotIn("E2", result.qualified_levels)
        self.assertTrue(any("preregistration" in error and "protocolSha256" in error
                            for error in result.errors))

    def test_preregistration_receipt_rejects_trusted_issuer_identity_substitution(self):
        record = make_record(level="E2", case_design="held-out", case_count=3)
        preregistration = record["trial"]["protocol"]["preregistration"]
        substituted_policy = copy.deepcopy(TEST_POLICY)
        substituted_policy["trustedReceiptIssuers"]["second-evidence-authority"] = {
            "algorithm": "rsa-pkcs1v15-sha256",
            "modulusHex": TEST_PUBLIC_MODULUS,
            "exponent": 65537,
        }
        preregistration["binding"]["issuerId"] = "second-evidence-authority"
        refresh_attempt_receipts(record)
        result = evidence.validate_semantics(
            Path("fixture.json"), record, substituted_policy, TASKS, ROOT, AS_OF
        )
        self.assertNotIn("E2", result.qualified_levels)
        self.assertTrue(any("signed receipt signature verification failed" in error
                            for error in result.errors))

    def test_evaluator_signature_binds_e4_production_result_fields(self):
        record = make_record(
            level="E4", case_design="production", case_count=20,
            accepted=True, spread_days=True,
        )
        arm = record["arms"][0]
        attempt = arm["attempts"][0]
        criterion = attempt["acceptance"]["criterionResults"][0]
        original_signature = criterion["receiptSignature"]
        mutations = {
            "accountable owner": (("production", "accountableOwnerId"), "owner-mutated"),
            "event issuer": (("production", "eventLedgerIssuerId"), "data-issuer-mutated"),
            "event signature": (("production", "eventLedgerSignature"), "x" * 172),
            "incident ledger": (("production", "incidents"), [{
                "incidentId": "incident-mutated",
                "severity": "S1",
                "discoveredAt": "2026-07-15T12:00:00+00:00",
                "description": "A changed production incident.",
                "customerImpact": "None",
                "status": "resolved",
                "deploymentId": "deployment-1",
                "armId": "arm-ai-only",
                "stackId": "stack-1",
                "attemptIds": ["attempt-ai-only-1"],
            }]),
            "outcome value": (("production", "downstreamOutcomes", 0, "value"), 0.95),
            "outcome signature": (
                ("production", "downstreamOutcomes", 0, "outcomeSignature"),
                "y" * 172,
            ),
        }
        for label, (path, replacement) in mutations.items():
            with self.subTest(production_field=label):
                changed = copy.deepcopy(record)
                target = changed
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = replacement
                changed_arm = changed["arms"][0]
                changed_attempt = changed_arm["attempts"][0]
                changed_criterion = changed_attempt["acceptance"]["criterionResults"][0]
                payload = evidence.canonical_json_bytes(
                    evidence.criterion_receipt_payload(
                        changed, changed_arm["armId"], changed_attempt, changed_criterion
                    )
                )
                self.assertFalse(evidence.verify_rsa_pkcs1v15_sha256(
                    payload,
                    original_signature,
                    TEST_PUBLIC_MODULUS,
                    65537,
                ), label)

    def test_auxiliary_evidence_bytes_are_bound_without_receipt_self_reference(self):
        record = make_record(case_count=2)
        criterion = record["arms"][0]["attempts"][0]["acceptance"]["criterionResults"][0]
        auxiliary = artifact("auxiliary-evaluation-1", "evaluation", content=b"original evidence")
        record["artifacts"].append(auxiliary)
        criterion["evidenceArtifactIds"].append(auxiliary["artifactId"])
        refresh_attempt_receipts(record)
        self.assertEqual(validate(record).errors, [])

        replacement = artifact(
            "auxiliary-evaluation-1", "evaluation", content=b"changed evidence"
        )
        upsert_artifact(record, replacement)
        result = validate(record)
        self.assertEqual(result.qualifying_ai_arm_ids["E1"], [])
        self.assertTrue(any("trusted evaluator signature" in error for error in result.errors))

    def test_evaluator_receipt_cannot_be_reused_as_cross_attempt_auxiliary_evidence(self):
        record = make_record(case_count=2)
        attempts = record["arms"][0]["attempts"]
        first_criterion = attempts[0]["acceptance"]["criterionResults"][0]
        second_receipt = attempts[1]["acceptance"]["criterionResults"][0]["receiptArtifactId"]
        first_criterion["evidenceArtifactIds"].append(second_receipt)
        refresh_attempt_receipts(record)
        result = validate(record)
        self.assertEqual(result.qualifying_ai_arm_ids["E1"], [])
        self.assertTrue(any("another criterion's evaluator receipt" in error
                            for error in result.errors))

    def test_deleting_another_attempt_invalidates_remaining_evaluator_receipts(self):
        record = make_record(case_count=2)
        record["arms"][0]["attempts"].pop()
        result = validate(record)
        self.assertEqual(result.qualifying_ai_arm_ids["E1"], [])
        self.assertTrue(any("trusted evaluator signature" in error for error in result.errors))

    def test_future_downstream_outcome_cannot_support_e4(self):
        record = make_record(
            level="E4", case_design="production", case_count=20,
            accepted=True, spread_days=True,
        )
        outcome = record["production"]["downstreamOutcomes"][0]
        outcome["periodStart"] = "2030-01-01"
        outcome["periodEnd"] = "2030-01-31"
        result = validate(record)
        self.assertTrue(any("ends in the future" in error for error in result.errors))

    def test_generic_release_labels_do_not_establish_immutable_stack(self):
        record = make_record(level="E2", case_design="held-out", case_count=3)
        stack = record["testedStacks"][0]
        stack["model"]["immutableRelease"] = {
            "kind": "provider-snapshot", "identifier": "gpt-5"
        }
        stack["orchestrator"]["immutableRelease"] = {
            "kind": "provider-snapshot", "identifier": "v1"
        }
        stack["tools"][0]["immutableRelease"] = {
            "kind": "provider-snapshot", "identifier": "stable"
        }
        refresh_preregistration(record)
        result = validate(record)
        self.assertEqual(result.qualifying_ai_arm_ids["E2"], [])
        self.assertTrue(any("immutable stack provenance" in error for error in result.errors))

    def test_e1_also_requires_reproducible_immutable_stack(self):
        record = make_record()
        for component in (
            record["testedStacks"][0]["model"],
            record["testedStacks"][0]["orchestrator"],
            record["testedStacks"][0]["tools"][0],
        ):
            component.pop("immutableRelease")
        result = validate(record)
        self.assertEqual(result.qualifying_ai_arm_ids["E1"], [])
        self.assertTrue(any("immutable stack provenance" in error for error in result.errors))

    def test_recursive_secret_scanner_covers_parameters_and_notes(self):
        record = make_record()
        record["testedStacks"][0]["model"]["parameters"]["api_key"] = "abcd1234"
        record["notes"] = "temporary password=hunter2"
        result = validate(record)
        self.assertTrue(any("api_key" in error and "forbidden" in error
                            for error in result.errors))
        self.assertTrue(any("credential pattern" in error for error in result.errors))

    def test_backdated_timestamp_without_external_receipt_cannot_qualify_e2(self):
        record = make_record(level="E2", case_design="held-out", case_count=3)
        del record["trial"]["protocol"]["preregistration"]
        result = validate(record)
        self.assertTrue(record["trial"]["protocol"]["preRegisteredAt"])
        self.assertTrue(any("externally bound preregistration" in error
                            for error in result.errors))

    def test_evaluated_criterion_without_receipt_cannot_qualify(self):
        record = make_record()
        record["arms"][0]["attempts"][0]["acceptance"]["criterionResults"][0][
            "evidenceArtifactIds"
        ] = []
        result = validate(record)
        self.assertEqual(result.qualifying_ai_arm_ids["E1"], [])
        self.assertTrue(any("has no auditable receipt" in error for error in result.errors))

    def test_preregistration_digest_detects_post_hoc_case_deletion(self):
        record = make_record(level="E2", case_design="held-out", case_count=4)
        failed = record["arms"][0]["attempts"][-1]
        failed["acceptance"]["overall"] = "rejected"
        failed["acceptance"]["criterionResults"][0]["result"] = "fail"
        failed["measurements"]["quality"] = 0.2
        refresh_preregistration(record)
        record["trial"]["cases"] = record["trial"]["cases"][:-1]
        record["arms"][0]["attempts"] = record["arms"][0]["attempts"][:-1]
        result = validate(record)
        self.assertTrue(any("protocolSha256 does not bind" in error
                            for error in result.errors))

    def test_plain_remote_artifact_is_claimed_only_and_cannot_qualify(self):
        record = make_record()
        output_id = record["arms"][0]["attempts"][0]["outputArtifactIds"][0]
        output = next(item for item in record["artifacts"] if item["artifactId"] == output_id)
        output["uri"] = "https://example.com/fake-output.json"
        result = validate(record)
        status = next(item["status"] for item in result.artifact_verification
                      if item["artifactId"] == output_id)
        self.assertEqual(status, "claimed-only")
        self.assertEqual(result.qualifying_ai_arm_ids["E1"], [])
        self.assertTrue(any("content-verifiable evidence" in error for error in result.errors))

        bypass = make_record()
        bypass_output_id = bypass["arms"][0]["attempts"][0]["outputArtifactIds"][0]
        bypass_output = next(
            item for item in bypass["artifacts"] if item["artifactId"] == bypass_output_id
        )
        bypass_output["uri"] = (
            f"https://example.com/sha256/{bypass_output['sha256']}"
        )
        bypass_result = validate(bypass)
        bypass_status = next(
            item["status"] for item in bypass_result.artifact_verification
            if item["artifactId"] == bypass_output_id
        )
        self.assertEqual(bypass_status, "claimed-only")
        self.assertEqual(bypass_result.qualifying_ai_arm_ids["E1"], [])

    def test_bare_digest_and_fake_git_commit_cannot_self_assert_e4(self):
        record = make_record(
            level="E4", case_design="production", case_count=20,
            accepted=True, spread_days=True,
        )
        for item in record["artifacts"]:
            item["uri"] = f"urn:sha256:{item['sha256']}"
        record["trial"]["protocol"]["preregistration"]["binding"] = {
            "kind": "git-commit", "immutableRef": "f" * 40
        }
        result = validate(record)
        self.assertEqual(result.qualifying_ai_arm_ids["E4"], [])
        self.assertTrue(any("git commit timestamp/path verification is unavailable" in error
                            for error in result.errors))
        self.assertTrue(all(item["status"] == "claimed-only"
                            for item in result.artifact_verification))

    def test_e4_requires_trusted_preregistered_sampling_and_event_ledger(self):
        record = make_record(
            level="E4", case_design="production", case_count=20,
            accepted=True, spread_days=True,
        )
        del record["trial"]["protocol"]["preregistration"]
        record["trial"]["protocol"]["preRegisteredAt"] = None
        record["artifacts"] = [
            item for item in record["artifacts"]
            if item["artifactId"] not in {
                "protocol-preregistration", "protocol-publication-receipt",
                "sampling-frame-1", "production-event-ledger-1",
            }
        ]
        result = validate(record)
        self.assertEqual(result.qualifying_ai_arm_ids["E4"], [])
        self.assertTrue(any("sampling/deployment plan was not preregistered" in error
                            for error in result.errors))

    def test_e4_exact_event_ledger_bytes_still_need_trusted_data_issuer_signature(self):
        record = make_record(
            level="E4", case_design="production", case_count=20,
            accepted=True, spread_days=True,
        )
        record["production"]["eventLedgerSignature"] = base64.b64encode(
            b"0" * 128
        ).decode("ascii")
        refresh_attempt_receipts(record)
        result = validate(record)
        self.assertEqual(result.qualifying_ai_arm_ids["E4"], [])
        self.assertTrue(any("event ledger lacks a trusted production-data signature" in error
                            for error in result.errors))

    def test_e4_locally_regenerated_outcome_value_needs_trusted_outcome_signature(self):
        record = make_record(
            level="E4", case_design="production", case_count=20,
            accepted=True, spread_days=True,
        )
        outcome = record["production"]["downstreamOutcomes"][0]
        outcome["value"] = 0.95
        locally_regenerated_bytes = evidence.canonical_json_bytes(
            evidence.downstream_outcome_payload(record, outcome)
        )
        upsert_artifact(record, artifact(
            outcome["evidenceArtifactIds"][0], "downstream",
            content=locally_regenerated_bytes,
        ))
        # The artifact bytes now exactly match the locally regenerated value,
        # but the trusted issuer did not sign that changed value.
        refresh_attempt_receipts(record)
        result = validate(record)
        self.assertEqual(result.qualifying_ai_arm_ids["E4"], [])
        self.assertTrue(any("trusted outcome-issuer signature" in error
                            for error in result.errors))

    def test_e4_data_and_outcome_issuer_trust_roles_are_not_interchangeable(self):
        outcome_mismatch = make_record(
            level="E4", case_design="production", case_count=20,
            accepted=True, spread_days=True,
        )
        outcome_mismatch["production"]["downstreamOutcomes"][0][
            "outcomeIssuerId"
        ] = "test-production-data-authority"
        refresh_preregistration(outcome_mismatch)
        outcome_result = validate(outcome_mismatch)
        self.assertEqual(outcome_result.qualifying_ai_arm_ids["E4"], [])
        self.assertTrue(any("trusted outcome-issuer signature" in error
                            for error in outcome_result.errors))

        ledger_mismatch = make_record(
            level="E4", case_design="production", case_count=20,
            accepted=True, spread_days=True,
        )
        ledger_mismatch["production"]["eventLedgerIssuerId"] = "test-outcome-authority"
        refresh_preregistration(ledger_mismatch)
        ledger_result = validate(ledger_mismatch)
        self.assertEqual(ledger_result.qualifying_ai_arm_ids["E4"], [])
        self.assertTrue(any("event ledger lacks a trusted production-data signature" in error
                            for error in ledger_result.errors))

    def test_e4_rejects_cross_attempt_output_and_receipt_reuse(self):
        record = make_record(
            level="E4", case_design="production", case_count=20,
            accepted=True, spread_days=True,
        )
        attempts = record["arms"][0]["attempts"]
        first_output = attempts[0]["outputArtifactIds"]
        first_receipt = attempts[0]["acceptance"]["criterionResults"][0]["evidenceArtifactIds"]
        for attempt in attempts[1:]:
            attempt["outputArtifactIds"] = list(first_output)
            attempt["acceptance"]["criterionResults"][0]["evidenceArtifactIds"] = list(first_receipt)
        refresh_production_artifacts(record)
        result = validate(record)
        self.assertEqual(result.qualifying_ai_arm_ids["E4"], [])
        self.assertTrue(any("reuses output" in error for error in result.errors))

    def test_fabricated_provider_snapshot_identifier_cannot_qualify(self):
        record = make_record(level="E2", case_design="held-out", case_count=3)
        for component in (
            record["testedStacks"][0]["model"],
            record["testedStacks"][0]["orchestrator"],
            record["testedStacks"][0]["tools"][0],
        ):
            component["immutableRelease"] = {
                "kind": "provider-snapshot", "identifier": "2099-99-99-fabricated"
            }
        refresh_preregistration(record)
        result = validate(record)
        self.assertEqual(result.qualifying_ai_arm_ids["E2"], [])

    def test_secret_key_variants_are_token_and_suffix_aware(self):
        for key in ("openai_api_key", "session_token", "accessToken", "clientSecretValue"):
            record = make_record()
            record["testedStacks"][0]["model"]["parameters"][key] = "live-value-1234"
            result = validate(record)
            self.assertTrue(any("forbidden credential-bearing field" in error
                                for error in result.errors), key)

    def test_hashed_local_artifact_bytes_are_scanned_for_credentials(self):
        record = make_record()
        output_id = record["arms"][0]["attempts"][0]["outputArtifactIds"][0]
        with tempfile.TemporaryDirectory(dir=ROOT / "evidence" / "records") as directory:
            path = Path(directory) / "unsafe.txt"
            path.write_text("openai_api_key=live-secret-value", encoding="utf-8")  # secret-scan: allow
            output = next(item for item in record["artifacts"] if item["artifactId"] == output_id)
            output["uri"] = str(path.relative_to(ROOT))
            output["sha256"] = evidence.sha256_file(path)
            refresh_attempt_receipts(record)
            result = validate(record)
        self.assertTrue(any("bytes contain a credential pattern" in error
                            for error in result.errors))

    def test_huge_human_prep_review_or_recovery_cannot_inflate_autonomy(self):
        record = make_record(level="E2", case_design="held-out", case_count=3)
        attempt = record["arms"][0]["attempts"][0]
        attempt["labor"]["preparationMinutes"] = 5000
        attempt["labor"]["reviewMinutes"] = 5000
        attempt["measurements"]["autonomousShare"] = 1
        refresh_attempt_receipts(record)
        result = validate(record)
        self.assertEqual(result.qualifying_ai_arm_ids["E2"], [])
        self.assertTrue(any("autonomousShare is inconsistent" in error for error in result.errors))

        recovery_record = make_record(level="E2", case_design="held-out", case_count=3)
        recovery_attempt = recovery_record["arms"][0]["attempts"][0]
        recovery_attempt["errors"].append({
            "errorId": "s2-rebuild",
            "severity": "S2",
            "detectedStage": "pre-release",
            "detectedBy": "human",
            "description": "A human rebuilt the output after an agent failure.",
            "evidenceArtifactIds": list(recovery_attempt["outputArtifactIds"]),
            "recovery": {
                "attempted": True,
                "successful": True,
                "minutes": 10000,
                "action": "Human rebuild",
                "artifactIds": list(recovery_attempt["outputArtifactIds"]),
            },
        })
        recovery_attempt["measurements"]["autonomousShare"] = 1
        refresh_attempt_receipts(recovery_record)
        recovery_result = validate(recovery_record)
        self.assertEqual(recovery_result.qualifying_ai_arm_ids["E2"], [])
        self.assertEqual(recovery_result.arm_metrics[0]["recoveryMinutes"], 10000)
        self.assertGreater(recovery_result.arm_metrics[0]["humanTouchMinutes"], 10000)

    def test_e4_outcome_failure_overrides_output_acceptance(self):
        record = make_record(
            level="E4", case_design="production", case_count=20,
            accepted=True, spread_days=True,
        )
        outcome = record["production"]["downstreamOutcomes"][0]
        outcome["baseline"] = 100
        outcome["target"] = 101
        refresh_preregistration(record)
        outcome["value"] = -999
        refresh_production_artifacts(record)
        result = validate(record)
        self.assertEqual(result.derived_interpretation, "does-not-support-capability")
        self.assertTrue(any("contradicts qualifying-arm outcomes" in error
                            for error in result.errors))

    def test_e4_outcome_receipt_must_bind_candidate_arm(self):
        record = make_record(
            level="E4", case_design="production", case_count=20,
            accepted=True, spread_days=True,
        )
        outcome = record["production"]["downstreamOutcomes"][0]
        outcome["armId"] = "unrelated-arm"
        refresh_preregistration(record)
        result = validate(record)
        self.assertEqual(result.qualifying_ai_arm_ids["E4"], [])

    def test_sensitive_inline_artifact_is_privacy_blocked(self):
        record = make_record()
        output_id = record["arms"][0]["attempts"][0]["outputArtifactIds"][0]
        output = next(item for item in record["artifacts"] if item["artifactId"] == output_id)
        output["access"] = "owner-only"
        output["containsSensitiveData"] = True
        output["redaction"] = "not-shareable"
        result = validate(record)
        status = next(item["status"] for item in result.artifact_verification
                      if item["artifactId"] == output_id)
        self.assertEqual(status, "privacy-blocked")
        self.assertEqual(result.qualifying_ai_arm_ids["E1"], [])

    def test_schema_catalog_rejects_unsupported_keywords(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            schema_dir = root / "schemas"
            policy_dir = root / "policies"
            schema_dir.mkdir()
            policy_dir.mkdir()
            unsafe_schema = copy.deepcopy(SCHEMA)
            unsafe_schema["allOf"] = [{"required": ["recordId"]}]
            (schema_dir / "1.0.json").write_text(json.dumps(unsafe_schema), encoding="utf-8")
            (policy_dir / "1.0.json").write_text(json.dumps(TEST_POLICY), encoding="utf-8")
            catalog = evidence.ValidationCatalog(schema_dir, policy_dir)
            with self.assertRaisesRegex(ValueError, "unsupported JSON Schema keyword 'allOf'"):
                catalog.validate_catalog()

    def test_policy_versions_coexist_and_are_selected_per_record(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            schema_dir = root / "schemas"
            policy_dir = root / "policies"
            schema_dir.mkdir()
            policy_dir.mkdir()
            (schema_dir / "1.0.json").write_text(json.dumps(SCHEMA), encoding="utf-8")
            (policy_dir / "1.0.json").write_text(json.dumps(TEST_POLICY), encoding="utf-8")
            policy_v2 = copy.deepcopy(TEST_POLICY)
            policy_v2["policyVersion"] = "2.0"
            policy_v2["qualification"]["E2"]["minimumDistinctCases"] = 4
            (policy_dir / "2.0.json").write_text(json.dumps(policy_v2), encoding="utf-8")

            v1_record = make_record(level="E2", case_design="held-out", case_count=3)
            v2_record = make_record(level="E2", case_design="held-out", case_count=3)
            v2_record["claim"]["policyVersion"] = "2.0"
            v1_path = root / "v1.json"
            v2_path = root / "v2.json"
            v1_path.write_text(json.dumps(v1_record), encoding="utf-8")
            v2_path.write_text(json.dumps(v2_record), encoding="utf-8")
            catalog = evidence.ValidationCatalog(schema_dir, policy_dir)
            results = evidence.validate_all(
                [v1_path, v2_path], catalog, TASKS, ROOT, AS_OF
            )
            summary = evidence.build_summary(results, AS_OF, catalog)
        self.assertEqual(results[0].errors, [])
        self.assertTrue(any("E2 evidence overclaim" in error for error in results[1].errors))
        self.assertEqual(summary["schemaVersions"], ["1.0"])
        self.assertEqual(summary["policyVersions"], ["1.0", "2.0"])

    def test_signed_or_credentialed_artifact_uris_are_rejected(self):
        for uri in (
            "https://user:password@example.com/artifact",
            "https://example.com/artifact?token=secret-value",
            "https://example.com/artifact#signed-secret",
        ):
            record = make_record()
            record["artifacts"][0]["uri"] = uri
            result = validate(record)
            self.assertTrue(any("URI appears to contain" in error for error in result.errors))


if __name__ == "__main__":
    unittest.main()
