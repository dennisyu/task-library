# Contributing task contracts and capability evidence

The Task Library catalogs bounded tasks and the instructions for completing
them. It is not a job-replacement forecast, an earnings model, or a promise that
an AI can complete a task autonomously.

Start with one intake lane:

- [New or repaired task contract](https://github.com/Goodrich-Dev/task-library/issues/new?template=task-contract.yml) — add a task, repair its canonical page or skill, or close a context/access/QA gap.
- [Capability evidence trial proposal](https://github.com/Goodrich-Dev/task-library/issues/new?template=evidence-trial.yml) — preregister a bounded test of an existing, frozen task contract.

An intake issue is a triage record, not proof. A merged skill can be
documentation-complete while its capability evidence remains E0.

## The two truth systems

Keep catalog readiness and capability evidence separate:

| System | What it says | What it does not say |
|---|---|---|
| `complete` / `needs-work` / `gap` | Whether the exact task page, definitive article, skill, and examples meet the Task Library documentation standard | Whether AI performed the task successfully |
| E0 | A heuristic estimate with no validated trial | Measured capability or replacement exposure |
| E1-E4 | The strength of a validated trial design; the result is separately `supports-capability`, `mixed`, or `does-not-support-capability` | Guaranteed autonomy, earnings, employment, client results, payback, or job/sector replacement |

Only an append-only record in `evidence/records/` that passes
`build/validate_evidence.py` can establish effective E1-E4. A proposal, demo,
dashboard score, owner assertion, or successful-looking output cannot. Negative
and mixed trials belong in the ledger too.

## Task-contract review gate

A task contribution must make these items reviewable before it is marked
complete:

1. **Bounded outcome and trigger** — one task, one observable result, and when to run it.
2. **Owner and reviewer** — the owner maintains the contract; the reviewer has authority to accept, reject, or stop the work.
3. **Public URLs** — identify the exact page that teaches this bounded task and the one definitive article that owns the broader concept. They may be the same only when the page truly serves both roles. List duplicates and redirects instead of creating competing pages.
4. **Exact skill source** — identify the repository, exact path or URI, immutable revision, and exact source SHA-256 when the source exists. A branch such as `main` is useful for discovery but is not an evidence revision.
5. **Inputs, context, access, and privacy** — name required systems and permission scopes. Use least privilege. Never put passwords, tokens, private customer data, or unredacted credentials in an issue, skill, commit, or artifact.
6. **Acceptance criteria** — objective checks, with the safety- or outcome-critical checks identified. “Looks good” is not a criterion.
7. **Reviewer gates** — identify live publishing, spending, outreach, deletion, account changes, or other consequential actions that require human approval.
8. **Failure, rollback, and escalation** — specify stop conditions, how to reverse a partial change, and who receives an unresolved exception.
9. **Receipts** — link real examples or say explicitly that an example is still needed. Do not fabricate evidence to make a task look ready.

Safe claim language is narrow: “This stack passed 4 of 5 preregistered cases
under these conditions” can be evidence. “AI replaces this role,” “students will
earn $X,” or “this pays back in Y days” is not supported by a task-level trial.
Any separate commercial or labor-market claim needs its own appropriately scoped
evidence and caveats.

## Skill package and registration

Use one folder per skill, with supporting files beside it:

```text
your-repo/
└── skills/
    └── your-task-slug/
        ├── SKILL.md
        └── references/
```

At minimum, a standard external `SKILL.md` has human-readable frontmatter:

```markdown
---
name: your-task-slug
description: One sentence describing the bounded outcome and intended operator.
---
```

Central Task Library skills must follow `Task-Library-Standard.md`, including
inputs, executable steps, a Definition of Done, examples, and definitive-article
links. The permanent slug must match the registered task.

Register through the Task Library tab of the Asset Tracker or propose a change
to `build/registry.json`. Supply the slug, category, documentation status, owner,
canonical article, and source. For an external source, prefer a commit-pinned
reference:

```text
github:<owner>/<repo>@<full-commit-sha>:skills/<slug>/SKILL.md
```

A release asset is preferable for a public download. A moving branch archive
may be used for work in progress, but it must not be presented as the exact
source tested by an evidence record.

## Evidence-trial operating loop

1. Freeze the task contract and exact skill digest.
2. Open a trial proposal. Name the owner, operator, evaluator, cases, arms, stack, permissions, acceptance rubric, artifact plan, and rollback.
3. Get reviewer approval before accessing private data or running a live, costly, destructive, or externally visible action.
4. Run every preregistered case. Preserve rejected, aborted, and unevaluated attempts rather than selecting only successes.
5. Add a new immutable record and hashed artifact references. Never rewrite an earlier completed record; supersede it with a new record.
6. Run the validator. Its result sets the effective evidence level and reports staleness, measured capability, supervision, cost, errors, and interpretation.
7. Feed failures back into the task contract. A changed skill digest or material change trigger requires a new trial; history remains visible.

The executable thresholds and record fields live in the append-only
`evidence/policies/1.0.json` and `evidence/schemas/1.0.json`. Add a higher
version instead of editing a released policy or schema; do not restate or
loosen them in a skill or issue.

## Local checks

Run the repository checks before requesting review:

```bash
python3 -m unittest discover -s build -p 'test_*.py'
python3 build/build.py
python3 build/validate_evidence.py --attach-to-task-data
python3 build/build_registry_surfaces.py --check
```

The maintainer triages task-contract changes first, then evidence proposals.
The reviewer records what was accepted, rejected, or returned for repair so the
next contributor can continue from a durable receipt rather than a chat summary.
