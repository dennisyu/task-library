---
name: write-meta-article-documenting-agent-work
description: Use the Meta-Article Prompt Template to document a real AI-agent task run as a publishable article — the proof layer that turns work into examples.
category: Content Factory — Process
stage: Process
definitive_article: /meta-article-prompt-template
status: complete
---

# Write meta-article documenting agent work

**Use this when** an AI agent (or human + agent) has just completed a real task run — any Task Library skill execution — and the run should become a linked example for its definitive article.

## Inputs
- The completed run: prompts used, tool outputs, before/after states, final deliverable
- The Meta-Article Prompt Template (the hub at /meta-article-prompt-template)
- The task's definitive article short URL (the hub this example will link up to)
- WordPress access for publishing per Blog Posting Guidelines

## Steps
1. Gather privacy-safe artifacts of the run while fresh: the exact prompts, key decisions, before/after evidence, output, failed attempts, and anything that went wrong. Record time, tokens, and cost only when auditable telemetry exists; otherwise say they were not captured or label assumptions explicitly.
2. Run the Meta-Article Prompt against those artifacts to draft the article: what the task was, why it was run, what the agent actually did step by step, and what resulted.
3. Show the real work — include the actual prompts and honest friction points. The value is reproducibility, not a polished success story.
4. State results concretely: what shipped, what changed, what was measured, who reviewed it, and whether each receipt is byte-verified, content-addressed, or asserted. Keep evidence level separate from whether the result was good.
5. Link the meta-article UP to its definitive article (one direction: example → hub). Never write the meta-article as a competing explanation of the concept — that is content vandalism; it documents one run.
6. Apply the entity-linking decision tree for every person, company, and concept mentioned.
7. Publish per the Blog Posting Guidelines pipeline (title <60, meta <160, keyword in first paragraph, real screenshots as images, RankMath 70+ at the Post stage).
8. Register the example: add it to the definitive article's examples section and the Task Library tracker. Registration improves documentation coverage; it does not award an E1–E4 evidence level by itself.

## Definition of done (QA checklist)
- [ ] Documents one real run with actual prompts and honest results — no hypotheticals
- [ ] Links up to the task's definitive article; does not compete with the hub
- [ ] Concrete outcomes stated (deliverable and measured metrics); unavailable telemetry is named, not invented
- [ ] Inputs, outputs, failed attempts, reviewer, rubric, and receipt status are inspectable without exposing credentials or private client data
- [ ] Complies with Blog Posting Guidelines (it publishes content)
- [ ] Example registered on the hub's examples list and in the tracker
- [ ] Linked back to the definitive article and relevant siblings

## Example(s)
- The hub at /meta-article-prompt-template carries linked examples that illustrate the structure. Verify the current set and evaluate each receipt on its own merits.

## Agent-assistance boundary (E0 until tested)

This task can be queued automatically after a run, but drafting, registration, and publication remain separate states. An agent may assemble a review-ready receipt while context is fresh; a named reviewer owns privacy, accuracy, evidence labeling, publication permission, and final registration. Failed or unpublished runs still belong in the evidence queue when they are safe to retain.
See `boil-the-ocean.md` for the full operating principles.

## Definitive article & links
- Hub: /meta-article-prompt-template
- Related: /blog-posting-guidelines (publishing pipeline), /internal-linking (its hub ships a skill file — a documented precedent), /knowledge-system-maintenance (capture loop)
- Sibling skills, in run order: any completed task run → this → `step-12-post-article-on-wordpress` (Post stage)
