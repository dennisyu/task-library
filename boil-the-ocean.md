# Boil the Ocean, Without Boiling Trust

This is the shared operating contract for expanding and improving the BlitzMetrics Task Library with human and AI workers.

"Boil the ocean" means follow the work across task, skill, evidence, article, distribution, and feedback boundaries until the outcome is durable. It does **not** grant unlimited authority, permit invented evidence, or turn a high AI score into permission to publish, spend, message, delete, or expose private data.

## The unit of work

Every run starts from one stable task slug and records:

1. The bounded outcome and non-goals.
2. The exact skill-source digest and frozen model/tool/access stack.
3. Inputs, privacy classification, authority, owner, reviewer, and stop conditions.
4. Acceptance criteria and rollback/escalation before live mutation.
5. Complete attempts, including failures, rework, supervision, and unavailable telemetry.
6. Inspectable outputs and evaluation receipts that are safe to retain.
7. What changed in the skill, article, tests, or policy after review.

An article, a skill, and an evidence record serve different purposes. Do not infer production reliability from documentation status or infer whole-job replacement from a bounded task result.

## Authority gates

- Read-only research, drafting, local analysis, and reversible tests can proceed inside the named scope.
- Credentials, private client material, consent, identity, relationships, spending, publication, external messages, account changes, destructive actions, and legal/compliance judgments keep a named human owner.
- Agents may prepare review-ready work for a gated action. They may not describe a draft, queued item, or saved rule as live execution.
- Stop when the target, owner, consent, privacy treatment, acceptance rule, or rollback path is ambiguous enough to change the outcome.

## Evidence rules

- E0 is a transparent hypothesis. It can prioritize testing; it cannot prove capability.
- E1–E4 require the current versioned policy and byte-verifiable, privacy-safe receipts. Claimed digests, model labels, memory prose, or timestamps are not proof by themselves.
- Report all planned cases and attempts. Never remove failures to improve a score or reuse one output as proof of many executions.
- Keep result interpretation separate from evaluation rigor. A rigorous trial may fail, and that failure is useful evidence.
- Do not invent time, token, cost, labor, or outcome numbers. Say "not captured" or label a scenario/estimate and its assumptions.
- Do not present task-level AI execution or automation exposure as a sector/job-loss probability.

## The improvement loop

1. **Observe:** inventory the task, canonical article, skill, owner, access, examples, evidence, and live URL health.
2. **Triage:** prioritize by outcome value, reuse, risk, current evidence, and the size of the known gap.
3. **Contract:** freeze the slug, source digest, stack, cases, rubric, owner/reviewer, privacy plan, and stop conditions.
4. **Run:** execute the smallest representative test and preserve complete, safe receipts.
5. **Review:** apply the rubric independently; record incidents, rework, and disagreement.
6. **Repair:** update the task, skill, article, redirect, test, or policy that caused the failure.
7. **Revalidate:** rebuild deterministic surfaces, rerun tests, audit the public result, and verify rollback.
8. **Teach:** publish a meta-article only when its claims and receipts are safe, accurate, and permissioned.
9. **Repeat:** promote claims only when the next evidence gate is actually satisfied.

## Current backlog signals

Use generated dashboard statistics rather than copying counts into this file. The useful queues include:

- tasks without a definitive article;
- skills with unverified agent-persistence, memory, autonomy, or named-model wording;
- tasks without an accountable owner or accepted example;
- stale or failing article-health findings;
- E0 tasks with high potential and representative cases ready for testing;
- negative trials and incidents that should become permanent regressions.

## Repository and deployment boundary

Evidence records, policy versions, and schema versions are intended to be append-only. CI can detect and block a build after a bad push, but it cannot undo a direct mutation to `main`. Maintainers must enforce a repository ruleset that requires pull requests and the append-only check, blocks force pushes/deletions, limits bypass, and protects the Pages deployment environment. Until that external control is verified, history is not independently immutable.

## Definition of done

A loop is complete only when the accepted outcome is inspectable, the named reviewer has signed off, live mutations are verified, errors became repairs or tests, public claims match evidence, generated surfaces are current, and the next unresolved boundary is explicit.

