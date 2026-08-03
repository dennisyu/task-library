# The BlitzMetrics Task Library Standard
### How every task becomes a definitive article + a skill.md + linked examples

**Source of truth:** [How to Create a Definitive Article for Any BlitzMetrics Concept](https://blitzmetrics.com/definitive-article-guide/) (v1.1, Apr 2026) and the [Task Library Dashboard](https://blitzmetrics.com/task-library-dashboard/).
**Purpose:** a single spec that any human or agent follows to bring every registered task up to standard — documented, downloadable as a skill, and wired into the SEO Tree. Counts are derived by the build; this standard never hard-codes them.

---

## The model: three artifacts per concept
Every concept/task in the library produces **three linked artifacts**, and they point at each other:

1. **Definitive article** — the one canonical page that owns the concept (the hub). Lives on blitzmetrics.com at a short URL.
2. **skill.md** — the machine-readable SOP an AI agent runs to *do* the task. Downloadable, one file per task. References its definitive article.
3. **Examples / meta-articles** — real proof the task was done, each documented with the Meta-Article Prompt and linking back up to the definitive article.

> Relationship (one direction up): **examples / meta-articles → definitive article → course/service**, and the definitive article links **across** to related definitive articles. Never publish a second page that competes with a hub (that's "content vandalism").

---

## The Nine Requirements of a Definitive Article
A page is only "definitive" if it meets **all nine**. Miss one and it's a draft (Yellow), not done (Green).

1. **Clear definition in the first two paragraphs** — what it is, what it is *not*, who it's for. Plain language, no unexplained jargon.
2. **The complete process / framework** — the full SOP, every stage/step/checklist. Detailed enough to follow without further instruction.
3. **Lots of real examples** — link *every* example that exists, not three or five. Each with a 1–2 sentence note on why it's relevant.
4. **Links to related concepts** — cross-link the other definitive articles (builds the entity graph).
5. **Links to the course/guide/service** — as a CTA near the bottom, not as the core content.
6. **Compliance with Blog Posting Guidelines** — title <60 chars; meta description <160; primary keyword in first paragraph; H2/H3 structure; short paragraphs; active voice; no AI-fluff phrases; no stock images; entity-linking decision tree for internal links.
7. **A short URL** — memorable redirect (e.g., `/dad`, `/digital-plumbing`) pointing to the hub, not the homepage or a case study.
8. **Visual diagram above the fold for multi-component concepts** — clickable, each node links to its section or sub-concept's definitive article. Must be visible without scrolling. If no multi-part diagram applies, still put *some* visual above the fold (no walls of text).
9. **Third-party endorsements / testimonials / E-E-A-T** — media, conference talks, podcasts, practitioner testimonials with proof. Highest-authority first; volume matters. (The `/dad` article is the gold standard.)

---

## The 10-Step Creation Process
Run in order for any task in a Yellow/Red (Needs Work / Gap) state:

1. **Identify the concept** and find every existing article that mentions it (the hub organizes them, doesn't replace them).
2. **Write the definition** (2 paragraphs; model on `/dad`).
3. **Document the process/framework** (the SOP — this is what the skill.md mirrors).
4. **Link every example** (1–2 sentences each).
5. **Cross-link related concepts** (other definitive articles).
6. **Link to the course/service** (CTA).
7. **Set the short URL** (redirect to the hub).
8. **Add the above-the-fold diagram** (if multi-component).
9. **Add E-E-A-T** (endorsements, testimonials, media — highest authority first).
10. **Publish, then run the Meta-Article Prompt** to create the companion meta-article that documents how it was built.

---

## Where definitive articles live in WordPress
- Published as a **Post** (not a Page).
- Assigned to the **Definitive Articles** category.
- Tagged with the **Content Factory stage** (`Stage: Produce | Process | Post | Promote`) and any cross-cutting **Topic:** tags. This lets agents pull, e.g., `category=definitive-articles&tag=stage-process` from the REST API.
- Authored in the **standard block editor (Gutenberg)** — **not Cornerstone** or any proprietary builder (builder content is opaque to AI agents and hard to update programmatically).

---

## The skill.md standard (one file per task)
Every task gets a `skill.md` an agent can run. House format — keep it tight, SOP-grade, and grounded in the definitive article:

```markdown
---
name: <kebab-case-task-slug>
description: <one sentence — what running this skill accomplishes, and for whom>
category: <one of the 13 library categories>
stage: <Produce | Process | Post | Promote | — >        # Content Factory stage if applicable
definitive_article: <short URL, e.g. /blog-posting-guidelines, or "GAP — to be written">
status: <complete | needs-work | gap>
---

# <Task Name>

**Use this when** <the trigger situation, in one line>.

## Inputs
- <what the agent/operator needs before starting>

## Steps
1. <imperative, concrete step>
2. ...
   (Mirror the definitive article's process exactly; this section IS the SOP.)

## Definition of done (QA checklist)
- [ ] <objective, checkable pass criteria — what "good" looks like>
- [ ] Linked back to the definitive article and relevant siblings
- [ ] Complies with Blog Posting Guidelines (if it publishes content)

## Example(s)
- <link to a real example / meta-article demonstrating this task>, 1–2 sentences on why it's relevant.
  (If none exists yet: "Example needed — run the Meta-Article Prompt after first real run.")

## Definitive article & links
- Hub: <short URL>
- Related: <sibling definitive articles / skills, in run order>
```

**Rules for skill.md authors (Fable workers):**
- The `name` slug is permanent (installs/bundles depend on it). Match the task slug.
- Steps must mirror the task's real SOP — use the definitive article's documented process, Dennis's frameworks (GCT, MAA, the 4 P's, SEO Tree, entity-linking decision tree, Dollar a Day mechanics), and the task description. No invented tools or fabricated URLs — reference only the task's real definitive-article short URL and known BlitzMetrics concepts.
- Every skill.md must carry a **Definition of done** checklist (the QA layer) and at least a placeholder **Example** so the meta-article loop has a slot to fill.
- For **gap** tasks (no article yet), set `definitive_article: GAP — to be written`, write the SOP from the description + method, and flag the missing hub.

---

## Examples = meta-articles
"Lots of real examples" (Requirement 3) is satisfied by **meta-articles** — each documents one real run of the task via the Meta-Article Prompt and links back to the definitive article. A task is fully "Green" when its definitive article exists, its skill.md is published, and it has at least one linked example/meta-article. The `/meta-article-prompt-template` (29 linked examples) and `/internal-linking` ("includes skill file for AI agents") are the models to copy.

---

## Status legend (matches the dashboard)
- **Complete (Green)** — definitive article exists and meets all nine requirements; skill.md present; ≥1 example.
- **Needs Work (Yellow)** — a page exists but misses ≥1 requirement, or has no skill.md / no example yet.
- **Gap (Red)** — no definitive article yet; skill.md is authored from the task definition and flags the missing hub.
