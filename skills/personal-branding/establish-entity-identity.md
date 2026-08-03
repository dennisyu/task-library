---
name: establish-entity-identity
description: Lock one consistent name, domain, and headshot across the entire web so Google can reconcile a single entity worthy of a Knowledge Panel.
category: Personal Branding
stage: —
definitive_article: /what-is-a-knowledge-panel
status: needs-work
---

# Establish entity identity

**Use this when** opening Phase 4 (Knowledge Panel) — the consistency audit everything else in the phase depends on.

## Inputs
- The canonical name string, yourname.com, and the canonical headshot
- Full inventory of everywhere the person appears online: profiles, GBP, press, podcasts, speaker pages, directories
- The Person schema currently live on the entity home

## Steps
1. Confirm the canonical identity triplet: one name spelling, one domain (yourname.com), one current headshot. Every decision in this skill enforces those three.
2. Sweep the web for the person: every profile, bio, directory listing, press mention, podcast page, and speaker page. List each with its name spelling, photo, and link target.
3. Fix drift everywhere it is found: variant spellings, old headshots, outdated bios, dead links. Retire or redirect abandoned profiles — fragments split the entity signal.
4. Verify the entity home still answers who / what / why-trust and remains the page every property points back to.
5. Check the Person schema name, image, and url match the canonical triplet exactly, and that sameAs covers all live properties (implement-technical-schema-markup handles the full upgrade).
6. Re-run this audit quarterly — identity drift is the most common reason a panel never forms or shows wrong facts.

## Definition of done (QA checklist)
- [ ] One name spelling, one domain, one current headshot across every property found in the sweep
- [ ] No live duplicates, abandoned variants, or outdated photos remain
- [ ] Schema matches the canonical triplet; sameAs current
- [ ] Quarterly re-audit scheduled
- [ ] Linked back to the definitive article and relevant siblings
- [ ] Complies with Blog Posting Guidelines (if it publishes content)

## Example(s)
- Harry Gold (harryjgold.com) and Cam Hazzard (camhazzard.com) — both brands anchor the exact personal name as domain and entity, the consistency pattern this skill enforces.

## Run on a persistent agent (Fable 5)
A persistent agent (Claude Fable 5 or a comparable OpenAI/Google model) is the right tool for a full-web sweep: it inventories every property where the person appears, fixes drift item by item, and loops until the Definition-of-done fully passes — one name, one domain, one headshot everywhere — not 90%.
It self-verifies by re-checking each fixed property against the canonical triplet held in memory since the Phase 1 Plumbing runs.
Because it persists, the quarterly re-audit actually happens, and the clean identity map it stores in memory is the foundation the rest of the Knowledge Panel phase builds on; a meta-article example is logged each run so the brand compounds.
See `boil-the-ocean.md` for the full operating principles.

## Definitive article & links
- Hub: /what-is-a-knowledge-panel
- Related: /personal-brand · builds on: add-consistent-headshots-and-bios-across-profiles · next: build-third-party-validation
