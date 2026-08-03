# Task capability evidence records

The dashboard's E0 values are inexpensive hypotheses. Files in `evidence/records/`
are the append-only trial ledger that can earn E1-E4 evidence. A higher evidence
level means the evaluation is stronger; it does **not** mean the AI performed
well. The trial's acceptance rate, measured capability, failures, supervision,
cost, and result interpretation carry that meaning.

## One record, one versioned trial

Each JSON record binds all of the following together:

- one Task Library slug and an exact resolved-source skill revision plus SHA-256 digest;
- an externally bound protocol, case/input manifest, planned arms, acceptance
  rubric, evaluator arrangement, and preregistered primary comparison for E3;
- every tested model/tool/context/permission stack, without credentials, plus
  byte-verified release artifacts for every stack component;
- Human-only, AI-only, and/or Human+AI arms with case-level attempts;
- acceptance outcomes, quality/scope/generalization measurements, time, cost,
  preparation, supervision, interventions, errors, detection stage, and recovery;
- production incidents and downstream outcomes when E4 is claimed;
- a review deadline and the material changes that force a retest.

Never overwrite a completed record to make a result look better. Correct or
extend it with another record and list the earlier ID in `supersedesRecordIds`.
Artifacts may live elsewhere, but each reference must include a content digest.
Do not put tokens, passwords, private customer data, or unredacted credentials
in this repository. The validator recursively scans the entire record, including
free-text notes and nested model parameters, for credential-bearing keys and
high-confidence secret patterns.

Every artifact has a declared SHA-256, but a declaration alone is not evidence.
An artifact used by a qualifying arm must expose bytes the validator can hash:
a repository-relative public file or a bounded public `data:` URI. Bare
`urn:sha256:`, `sha256:`, HTTP, and private-store references are `claimed-only`;
a digest string does not prove that bytes exist. Embedded/local bytes marked
restricted, owner-only, sensitive, or not-shareable are privacy-blocked and
cannot qualify. The validator also scans those bytes for credentials and common
PII patterns. It deliberately does not fetch remote or private URLs.

Provider-snapshot strings are nonqualifying until a trusted provider resolver
or signed provider receipt exists. `artifact-digest` stack releases must name a
byte-verified release artifact whose recomputed digest matches the identifier.

## Evidence gates

The executable thresholds live in `evidence/policies/1.0.json`; the matching
record structure lives in `evidence/schemas/1.0.json`. Each record selects its
exact `claim.policyVersion` and `schemaVersion`, and the validator loads that
pair instead of applying the newest policy retroactively.

| Level | Minimum claim this policy will accept |
|---|---|
| E0 | Heuristic only; represented by the dashboard, not a trial record |
| E1 | At least one accepted, evaluated AI-only or Human+AI demonstration with auditable receipts, content-verifiable artifacts, and an immutable stack |
| E2 | An externally preregistered repeated-case or held-out trial with at least three distinct evaluated cases in one qualifying AI-containing arm |
| E3 | A preregistered primary Human-only, AI-only, and Human+AI comparison, each evaluated on at least three identical cases with the same tested AI stack, a blinded peer/independent evaluator whose ID is disjoint from operators/recorder/owner, and paired, randomized, or counterbalanced assignment |
| E4 | A trusted-signed production plan and sampling frame, at least 20 evaluated production cases in one arm spanning 30 days, a complete byte-verified event ledger signed by a trusted production-data issuer, accountable owner, cost/supervision/incident capture, and a separately trusted outcome-issuer-signed arm/deployment-bound downstream outcome that meets its preregistered target and guardrails |

E2-E4 can validly report a negative result. That is why every record separately
declares `resultInterpretation` as `supports-capability`,
`does-not-support-capability`, or `mixed`.

Qualification is arm-local. Case count, coverage, attempt limits, measurements,
cost, and (for E4) the sustained date span must all hold in the same arm; they
cannot be assembled from unrelated partial arms. For E3, the primary comparison
is declared before execution and included in the external preregistration
digest. The public interpretation and metrics are derived only from the selected
qualifying arm(s), whose IDs are published as `qualifyingAiArmIds`,
`selectedAiArmIds`, and `selectedPublicArmIds`.

## Acceptance and measured capability

Every completed attempt is judged against the same protocol criteria. The
validator requires at least one critical criterion and a weighted threshold of
at least 0.7. It rejects an `accepted` label if a critical criterion failed, a
criterion was skipped, the threshold was missed, or an S3/S4 error occurred.
Every evaluated criterion must also cite at least one existing, allowed,
byte-verified evaluation receipt. Its signature binds a cycle-safe digest of
the complete result-affecting record, including record/trial identity, task and
skill, protocol, arm and stack, attempts, acceptance, measurements, outputs and
auxiliary evidence digests, timing, labor, cost, errors, recovery, claim, and
interpretation. The signature must verify against a policy-trusted evaluator
key, and receipt bytes cannot be reused across attempts.

Policy 1.0 intentionally ships with all four trust maps empty: preregistration
receipt authorities, evaluators, production-data issuers, and downstream-outcome
issuers. No real E1-E4 record can qualify until maintainers provision reviewed
public keys in a new higher, append-only policy version; synthetic test keys
exist only inside the test process and are not trusted by repository policy.
Before activation, every configured key is validated as RSA PKCS#1 v1.5 with
SHA-256, public exponent 65537, a canonical odd modulus between 2048 and 8192
bits that is coprime to the exponent, and no unrecognized metadata fields. A
signature must decode to the exact modulus width and its integer must be smaller
than the modulus. Malformed keys fail catalog loading and semantic validation;
an exponent-1 no-private-key forgery is retained as an end-to-end regression.

`preparationMinutes` records human input staging before a run;
`operatorMinutes` records human execution of the task; `supervisionMinutes`
records active oversight or intervention; and `reviewMinutes` records post-run
QA. An AI-only arm may still incur preparation and review, but it cannot hide
human task execution or active intervention. The validator derives a consistency
bound for `autonomousShare` from elapsed time, preparation, active human work,
review, and recovery. Recovery minutes are included in human-touch/supervision
totals; an arbitrary human rebuild cannot preserve a high-autonomy claim.

For each AI-containing arm the validator reports:

```text
TCI = 100 * (quality * reliability * autonomousShare
             * endToEndScope * generalization) ** (1/5)
```

The component means come from case-level measurements; reliability is the share
of all attempts accepted, so aborted and selectively unevaluated runs remain in
the denominator. Preregistered cases must have distinct input digests and full
attempt coverage, and E2+ permits at most one attempt per case/arm; recovery is
recorded inside that attempt. Zero in any component therefore produces zero
rather than being hidden by an arithmetic average. A known-case E1 demonstration
does not establish generalization, so it reports component results but no full
TCI. Repeated or held-out evidence must supply that dimension before TCI is shown.

## Freshness

A record is excluded from the task's **effective** level when:

- its explicit `reviewDueAt` has passed;
- the policy's maximum age has passed;
- the current built skill's exact resolved-source SHA-256 differs from the tested digest; or
- the current skill path no longer exists.

Model, tool, context, permission, acceptance-rule, or environment changes cannot
be discovered reliably from this repository alone. The record must list those
material-change triggers, and the operator must create a new trial when one
fires. Historical records stay in the ledger even after they become stale.

## Validate and build an overlay

Run this after `build/build.py`, because `dashboard/data.json` includes tracker
and spoke tasks that may not appear in the local registry:

```bash
python3 build/validate_evidence.py \
  --task-data dashboard/data.json \
  --records evidence/records \
  --out dashboard/evidence-summary.json \
  --attach-to-task-data
```

The command exits nonzero for malformed records, unresolved references,
acceptance inconsistencies, or evidence overclaims. Staleness is reported and
automatically downgrades the effective level, but is only a failing condition
when `--strict-stale` is supplied.

The generated summary is an overlay keyed by task slug. A build integration
should attach `tasks[slug]` under a distinct task `evidence` field. It may show
`effectiveEvidenceLevel` as the validated evidence label, but it must not present
the original E0 heuristic number as a measured score. Measured TCI values live
in the winning record's `armMetrics`, separated by AI-only and Human+AI arm.
Never copy a record's claimed level without running this validator.

## Immutable validation history

Records and the policy/schema files that interpret them are append-only. Never
edit `evidence/policies/1.0.json` or `evidence/schemas/1.0.json` after release.
Introduce a strictly higher filename and matching internal version instead. A
new policy may reference an existing schema; both old and new policies continue
to validate records that select them. The generated ledger therefore publishes
`schemaVersions` and `policyVersions`, while each task/record publishes its
exact selected pair.

`build/check_evidence_append_only.py` is preventive only when a repository
ruleset requires its pull-request check before merge. On a direct push, Actions
runs after the mutation, so the push-mode check is only an alarm/build blocker;
it cannot undo the write, and a later run could otherwise accept the rewritten
commit as its base. Maintainers must configure an external ruleset that blocks
direct/force pushes to `main`, requires PRs plus this check, and tightly
restricts bypass. Until that ruleset and a deploy provenance gate are verified,
append-only history is an unresolved maintainer control and deployment must not
be described as protected by CI alone.

## Create a record

1. Copy the shape from `evidence/schemas/1.0.json`; generate a UUID for
   `recordId` and a stable ID for the trial.
2. Hash the exact skill source and every artifact with SHA-256. Do not trim a terminal newline: the catalog's `sourceSha256` is computed before dashboard presentation normalization. For a pathless legacy catalog where the field is absent, the validator labels and warns when it must use the deterministic stored-content fallback. An explicit `sourceSha256: null` means no resolved skill exists and cannot qualify for E1-E4; if neither an exact catalog digest, local path, nor legacy content is available, validation fails closed.
3. Before E2-E4 execution, publish the protocol bytes and obtain a receipt signed
   by a policy-trusted authority. The signed digest binds the task/skill, trial
   window, full cases/inputs, operators/arms, context/permissions/parameters,
   stack releases, rubric/evaluator, E3 primary comparison, and E4 sampling,
   deployment, and outcome definitions. An unverified git SHA or backdated
   `preRegisteredAt` field does not qualify.
4. Record each attempt, including rejected/aborted work and zero-error arrays.
5. Run the validator locally and commit the record plus any non-sensitive
   evidence artifacts or durable external references.
6. Review a generated diff before exposing the upgraded evidence level.

The custom runtime supports only the JSON Schema keywords explicitly audited in
`build/validate_evidence.py`; catalog loading rejects any unknown keyword rather
than silently ignoring newer Draft 2020-12 behavior. Run
`python3 build/scan_repository_secrets.py` before build/deploy as an additional
working-tree credential check. Its privacy heuristics are deliberately limited
and do not replace human privacy review.
