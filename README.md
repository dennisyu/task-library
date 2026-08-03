# BlitzMetrics Task Library

Hub-and-spoke skill library. This repo is the **hub**: the registry, the dashboard, and the default home for skill files. Skills can also live in their owner's own repo (the **spokes**) — the build pulls them in at build time.

## Layout

```
skills/<category-folder>/<slug>.md   skill files that live in this repo ("local")
build/registry.json                  slug -> source; THE index of the library
build/categories.json                the 13 categories (order, icons, colors)
build/site-meta.json                 bundle URL, meta-article URL, updated label
build/build.py                       resolve -> validate -> compose dashboard/data.json
build/build_registry_surfaces.py     data.json -> task-registry.json + llms.txt
build/task-registry.schema.json      versioned contract for machine clients
build/validate_evidence.py           E1-E4 ledger validator + task overlay
build/audit_public_articles.py       bounded, SSRF-safe public article health audit
build/check_repository_governance.py fail-closed external ruleset gate for trusted deploys
evidence/                            schema, policy, append-only trial records
dashboard/                           index.html + app.js + generated data.json
Task-Library-Standard.md             the spec every skill.md must meet
boil-the-ocean.md                    shared authority, evidence, privacy, and improvement-loop contract
.github/workflows/build.yml          CI: build + deploy to GitHub Pages
```

> **Bringing your own skill repo?** See [CONTRIBUTING-SKILLS.md](CONTRIBUTING-SKILLS.md) — the full guide to formatting and registering an external skill (spoiler: if it's a normal Claude skill, it already qualifies).

## Owning a skill in your own repo

Nobody edits this repo to own a skill. Everything happens in the **Asset Tracker's Task Library sheet**:

1. Put your `SKILL.md` in your repo at `skills/<slug>/SKILL.md` (standard Claude skill format — `name` + `description` frontmatter, `name` = the slug).
2. On your skill's row in the sheet: put your name in **Owner**, your repo URL in **Source Repo**, and set **Status** (`wip` while you work it, `ready` when you stand behind it).
3. Done. The next build (daily, or manual run) fetches your file, and if a hub draft existed it's superseded automatically. From then on you only ever push to your own repo.

The precedence rule: **sheet beats registry beats hub file** — a skill has exactly one live source, and the sheet's Source Repo cell is the switch. The Slug column completes the address, so a bare repo URL is enough when you follow the standard layout; use a deeper `/tree/` or `/blob/` link only if your file lives elsewhere.

`build/registry.json` is maintainer plumbing, not a contributor surface: it holds the hub-resident skills and the advanced cases (commit-SHA pinning, release-asset downloads). Fetch failures fall back to the last good cached copy, so a deleted repo never blanks the dashboard. Private repos need `SKILLS_READ_TOKEN` set in Actions secrets.

## Validation

`build/build.py` rejects skills that: lack frontmatter or any required field, have `name` ≠ slug, use an unknown category/stage/status, or miss required sections (Inputs, Steps, Definition of done, Examples, Definitive article & links). It warns (build passes) on: stub language in a `complete` skill, <3 numbered steps, frontmatter/registry category mismatch.

## Asset Tracker

The Asset Tracker's *Task Library* tab stays the ops-facing index (status, owner, flags). Publish it to web as CSV and set `TRACKER_CSV_URL` repo variable — the build then overrides `status`/`owner`/`article` per slug from the sheet. Content always comes from git; workflow state comes from the sheet.

The sheet is also the **onboarding path**: a row whose Slug isn't in the registry but has a Source Repo link becomes a new external skill on the next build — no PR to this repo needed. See CONTRIBUTING-SKILLS.md.

## SEO

The dashboard itself is `noindex` (it's a utility, not the ranking surface — and it must never compete with the hub articles from a github.io origin). The build also emits **`dashboard/library-index.html`**: a plain semantic HTML fragment — category H2s, every task with its description, its exact task page when one has been reviewed, and its broader definitive article. Paste it into the WordPress task-library page *below* the iframe (or template it in) so blitzmetrics.com serves an indexable representation of the library. Refresh the paste when mappings change materially; the fragment is deterministic, so a diff shows when.

`build/task-pages.json` is the reviewed crosswalk for exact SOP pages. An exact task page teaches the bounded task; a definitive article explains the broader concept. A page can legitimately serve both roles, but the build and coverage statistics never infer that relationship from a similar title or treat a broad hub as an exact SOP without review.

## Machine discovery

Every deploy also publishes four explicit discovery surfaces from the same `dashboard/data.json` used by the interactive library:

- **`/task-registry.json`** — a flattened, versioned registry. Each record has a stable slug, category/stage/status, separate exact-task-page, definitive-article, and dashboard links, source type, owner when known, capability scorecard, embedded skill Markdown, and exact source plus embedded-Markdown SHA-256 revisions.
- **`/task-registry.schema.json`** — the JSON Schema contract for clients and validators.
- **`/llms.txt`** — a compact map of the registry, bundles, methodology, interpretation rules, and current category inventory.
- **`/evidence-summary.json`** — validated E1-E4 results and history keyed by stable task slug.

These files are deployment artifacts and are intentionally ignored in git; Actions regenerates them after `data.json` on every build. Commit the generator, source schema, and tests—not daily copies of the 1+ MB registry.

Trusted non-PR builds also run an observation-only public-article audit and write `/public-article-audit.json`. It checks HTTP/redirect state, meaningful page content, login interception, and canonical-link integrity without sending cookies. The audit is deliberately non-blocking while its baseline is established; `--strict` is available once maintainers have reviewed and dispositioned the live findings. Source hosts default to the configured task-library host and any additional source or redirect host must be explicitly allowlisted.

The companion exact-page audit writes `/task-page-audit.json`. It validates the reviewed crosswalk, checks mapped SOP pages, and compares the current catalog with task-like links already exposed by the legacy WordPress Task Library. Unmapped catalog tasks and unmapped legacy pages become explicit repair queues instead of being hidden by hub-level coverage.

The registry deliberately keeps documentation readiness, AI execution, human accountability, automation exposure, and evidence level separate. An E0 score is a low-confidence triage hypothesis, not proof of production reliability or a prediction of whole-job loss. Clients can compare `registryRevision` for any registry change and `skill.sha256` for an exact source change. Because dashboard Markdown is presentation-normalized, `skill.markdownSha256` separately verifies the embedded text. `skill.digestSource` distinguishes an exact `resolved-source` digest from a deterministic legacy fallback; a tracker-only gap with no skill source reports `sha256: null` and `digestSource: unavailable`, which cannot support E1-E4 evidence.

The current source corpus also contains widespread agent-persistence, memory, and model-specific design language. The build counts and flags those skills, reduces their readiness score, and exposes the note in task details and the machine registry. That language is an intended orchestration pattern—not evidence that the named stack can perform it. It remains E0 until a frozen stack and accepted trial satisfy the evidence policy.

## Capability evidence loop

`evidence/records/` is an append-only ledger. E1-E4 records bind the exact task and resolved-source skill hash to preregistered cases, immutable artifacts, the tested model/tool/access stack, acceptance results, human supervision, errors, recovery, and freshness. `build/build.py` computes `sourceSha256` before trimming Markdown for dashboard presentation, so a terminal newline cannot falsely stale a valid trial. Negative trials remain valid evidence; the level describes evaluation rigor, while the recorded outcomes describe performance.

The validator rejects duplicate case inputs, selective attempt reporting, non-finite measurements, unsafe acceptance thresholds, contradictory positive labels, unmatched E3 comparisons, skill drift, and stale evidence. CI also rejects edits or deletions of historical record files: corrections must be new records that supersede the old record.

## Local build

```
python3 build/build.py                       # data.json, static index, and skill bundles
python3 build/validate_evidence.py --attach-to-task-data
python3 build/build_registry_surfaces.py     # task-registry.json, schema, and llms.txt
python3 build/audit_public_articles.py --input dashboard/data.json --out dashboard/public-article-audit.json
python3 build/audit_task_pages.py --input dashboard/data.json --map build/task-pages.json --out dashboard/task-page-audit.json
python3 -m unittest discover -s build -p 'test_*.py'
python3 build/build_registry_surfaces.py --check
```
