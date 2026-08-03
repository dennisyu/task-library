---
name: process-through-content-factory
description: Turn an approved thank-you video into the smallest set of channel-fit assets that pass consent, attribution, and publishing acceptance checks.
category: Thank You Machine
stage: Process
definitive_article: /thank-you-machine
status: complete
---

# Process through Content Factory

**Use this when** a thank-you video has been recorded, sent privately, and approved for one or more clearly named public or owned-channel uses.

## Inputs
- The recorded thank-you clip, filed in the Content Library (person–trigger–date)
- The trigger row (person, deed, why it mattered, handle) — the metadata is the story
- Standard Content Factory access: transcription (Descript), WordPress, email tool

## Steps
1. Intake like any factory asset: upload to the Content Library and transcribe — the transcript supplies captions, quotes, and the written derivatives.
2. Select only channel-fit candidates supported by the source and consent record. Options can include a native social post, relevant blog excerpt, approved testimonial, ad candidate, or email mention; no run owes all five.
3. Record why each candidate fits its channel, who must approve it, and any use that is out of scope. A testimonial or paid-ad use requires explicit permission for that use.
4. Keep the person's name and the **specific deed** intact in every derivative. Gratitude generalized is gratitude deleted.
5. Apply Blog Posting Guidelines to anything proposed for publication: first-person voice, real photos, short paragraphs, no AI-fluff.
6. Entity-link per the decision tree: the person's name links to their personal site or profile; their company to its site; concepts to definitive articles.
7. Stage only accepted candidates in the publishing queue with verified handles, approval status, and a named reviewer. Do not publish or spend without the configured permission gate.

## Definition of done (QA checklist)
- [ ] Each selected derivative has a recorded channel-fit reason; skipped formats are not counted as failures
- [ ] Name + specific deed intact in every asset; permission scope confirmed for endorsement, paid, and public uses
- [ ] Published pieces follow Blog Posting Guidelines and the entity-linking decision tree
- [ ] Accepted assets staged with verified handles, approval state, and named reviewer; no unauthorized publish/spend action
- [ ] Linked back to the definitive article and relevant siblings
- [ ] Complies with Blog Posting Guidelines (if it publishes content)

## Example(s)
- Example needed — run the Meta-Article Prompt after the first accepted run, recording which formats were selected or skipped, why, and the approval receipt for each use.

## Agent-assistance boundary (E0 until tested)
Agent assistance can draft and check channel candidates, but the named reviewer owns source fidelity, consent scope, endorsement use, publishing, and spend. Output count is a measured run result, not a fixed promise.
Log each accepted run via the Meta-Article Prompt, including skipped candidates and failed checks, so the library can learn from complete outcomes.
See `boil-the-ocean.md` for the full operating principles.

## Definitive article & links
- Hub: /thank-you-machine
- Related: /content-factory (the parent pipeline) · /blog-posting-guidelines (publishing standard) · /dad (where the ad-creative cut goes)
- Run order (TYM): record-one-minute-thank-you-video → **process-through-content-factory** → tag-the-person-on-social-media
