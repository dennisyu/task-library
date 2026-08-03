---
name: build-third-party-validation
description: Accumulate the independent proof — press, Wikipedia/Wikidata, podcasts, books — Google needs before it will trust the entity with a Knowledge Panel.
category: Personal Branding
stage: —
definitive_article: /what-is-a-knowledge-panel
status: needs-work
---

# Build third-party validation

**Use this when** entity identity is locked and the panel needs evidence Google did not get from the person's own properties — Phase 4 (Knowledge Panel).

## Inputs
- The validation inventory built during Phase 3 (press, podcasts, talks, collaborations)
- An honest assessment of notability: real independent coverage, not self-published claims
- The canonical name string and yourname.com

## Steps
1. Maintain a single validation inventory: every press mention, podcast episode, speaker page, book credit, and directory entry — with URL, date, and whether it links to yourname.com.
2. Keep earning the staples through the Phase 3 skills: press mentions in recognized publications and podcast features — the trusted-source signals Google weighs most.
3. Pursue a Wikidata entry when independent sources exist to cite; pursue Wikipedia only if genuine notability and independent coverage support it — never self-promotional editing, which backfires on the entity.
4. Add book validation where credible: authored or contributed chapters create durable author-page proof.
5. Enforce consistency on every validation source: exact canonical name, current headshot where shown, link to yourname.com where editorially possible.
6. Surface the proof: cite the strongest validation on the brand site's press section and add profile-grade pages to the schema sameAs via implement-technical-schema-markup.

## Definition of done (QA checklist)
- [ ] Validation inventory current and growing quarter over quarter
- [ ] Press and podcast validation present; Wikidata/Wikipedia pursued only as notability honestly supports
- [ ] Every validation source uses the exact canonical name
- [ ] Strongest proof cited on the brand site and reflected in schema
- [ ] Linked back to the definitive article and relevant siblings
- [ ] Complies with Blog Posting Guidelines (if it publishes content)

## Example(s)
- Example needed — run the Meta-Article Prompt after first real run.

## Run on a persistent agent (Fable 5)
A persistent agent (Claude Fable 5 or a comparable OpenAI/Google model) maintains the validation inventory as a living memory object: every press hit, episode, speaker page, and book credit produced by the Phase 3 skills lands there with URL, date, and link status, and the agent loops until each quarter's Definition-of-done fully passes — not 90%.
It self-verifies notability honestly — pursuing Wikidata or Wikipedia only when independent sources support it — and re-checks every source for the exact canonical name.
It surfaces the strongest proof to the brand site and the schema skill automatically, and logs a meta-article example each run (this file still needs its first) so the brand compounds.
See `boil-the-ocean.md` for the full operating principles.

## Definitive article & links
- Hub: /what-is-a-knowledge-panel
- Related: /personal-brand · feeds from: get-mentioned-in-publications · get-featured-on-podcasts · next: implement-technical-schema-markup
