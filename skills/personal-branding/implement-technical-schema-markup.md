---
name: implement-technical-schema-markup
description: Upgrade the entity's structured data — Person or Organization schema with a complete, verified sameAs graph — to Knowledge Panel grade.
category: Personal Branding
stage: —
definitive_article: /what-is-a-knowledge-panel
status: needs-work
---

# Implement technical schema markup

**Use this when** Phase 4 is underway and the basic Phase 1 Person schema must carry every verified profile and validation page — Phase 4 (Knowledge Panel).

## Inputs
- The Phase 1 Person schema currently live on yourname.com
- Complete list of verified profiles plus durable validation pages (podcast guest profiles, speaker pages, Wikidata entry if it exists)
- Current facts: role, organization, expertise topics

## Steps
1. Choose the entity type deliberately: Person for the personal brand; Organization for the business; where both exist, publish both and relate them (the Person worksFor the Organization).
2. Audit the existing Phase 1 schema against current facts — names, roles, and images go stale as the brand grows.
3. Extend the sameAs array beyond the core five profiles to every verified, durable property: GBP, podcast guest profiles, speaker pages, directory listings, Wikidata. Every entry must be live and unmistakably the same person.
4. Add supporting properties only as facts allow — jobTitle, worksFor, alumniOf, knowsAbout, image — every claim verifiable on the linked pages. Schema is testimony, not marketing.
5. Validate with Google's Rich Results Test / schema validator to zero errors, and re-check that visible page copy matches every schema claim.
6. Put schema maintenance on a trigger: any new validated profile, press feature, or role change updates the markup within the week.

## Definition of done (QA checklist)
- [ ] Correct entity type(s) published; validator returns zero errors
- [ ] sameAs covers every verified profile and durable validation page — all live, all the same person
- [ ] Every schema property verifiable; schema matches on-page copy and published bios
- [ ] Update trigger documented in the maintenance routine
- [ ] Linked back to the definitive article and relevant siblings
- [ ] Complies with Blog Posting Guidelines (if it publishes content)

## Example(s)
- Example needed — run the Meta-Article Prompt after first real run.

## Run on a persistent agent (Fable 5)
A persistent agent (Claude Fable 5 or a comparable OpenAI/Google model) upgrades the Phase 1 schema using everything memory has accumulated across the phases — verified profiles, podcast guest pages, speaker pages, Wikidata — and loops validate → fix → revalidate until zero errors and the full Definition-of-done passes, not 90%.
It self-verifies that every sameAs target is live and unmistakably the same person, and that every property claim is verifiable on the linked page.
Because it persists, the update trigger is real: new validation pages from Phase 3 runs get appended within the week, and a meta-article example is logged each run so the brand compounds.
See `boil-the-ocean.md` for the full operating principles.

## Definitive article & links
- Hub: /what-is-a-knowledge-panel
- Related: /personal-brand · upgrades: implement-person-schema-with-sameas-links · next: claim-and-verify-knowledge-panel-when-it-appears
