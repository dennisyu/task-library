---
name: add-schema-markup-person-localbusiness
description: Implement Person or LocalBusiness JSON-LD with sameAs links to every verified profile, stitching the brand into one machine-readable entity.
category: Digital Plumbing
stage: —
definitive_article: /digital-plumbing
status: needs-work
---

# Add Schema Markup (Person/LocalBusiness)

**Use this when** the site has no structured data, schema that fails validation, or schema whose sameAs list doesn't match the live social profiles.

## Inputs
- Canonical NAP record and the live URLs of every verified profile (Facebook, Instagram, YouTube, LinkedIn, Google Maps listing)
- Real headshot (Person) or logo (LocalBusiness) hosted on the site
- Website admin access (theme header or SEO plugin such as Rank Math)

## Steps
1. Choose the type: Person for a personal brand site, LocalBusiness for a service business. A personal brand fronting a business can use both, linked (Person worksFor → LocalBusiness).
2. Build the JSON-LD. Person: name, url, image (real headshot), jobTitle, worksFor, sameAs. LocalBusiness: name, url, image/logo, telephone, address, sameAs. Name, address, and telephone must match the canonical NAP character-for-character.
3. Fill sameAs with every live, verified profile URL — Facebook, Instagram, YouTube, LinkedIn, and the Google Maps listing. No dead or unclaimed profiles.
4. Install the JSON-LD site-wide via the SEO plugin or theme header — at minimum on the homepage and About page.
5. Validate with Google's Rich Results Test and the Schema Markup Validator: zero errors, and warnings reviewed.
6. Click every sameAs URL from the rendered source to confirm each resolves to the right profile.
7. Re-run this skill whenever a profile URL changes — stale sameAs links break the entity graph.

## Definition of done (QA checklist)
- [ ] JSON-LD present in page source on the homepage (and About page)
- [ ] Validates with zero errors in Rich Results Test / Schema Markup Validator
- [ ] sameAs lists all live profiles; every URL resolves correctly
- [ ] Schema NAP matches GBP and website NAP exactly
- [ ] Linked back to the definitive article and relevant siblings
- [ ] Complies with Blog Posting Guidelines (if it publishes content)

## Example(s)
- Example needed — run the Meta-Article Prompt after first real run.

## Run on a persistent agent (Fable 5)
A persistent agent (Claude Fable 5 or a comparable OpenAI/Google model) builds the JSON-LD, runs both validators, clicks every sameAs URL, and loops on each error until the full Definition of done passes — zero validation errors, not 90% of the checklist.
Because stale sameAs links break the entity graph, it keeps the canonical NAP and the live profile-URL set in memory and re-verifies them on every later run, logging a meta-article example each run so the library compounds.
See `boil-the-ocean.md` for the full operating principles.

## Definitive article & links
- Hub: /digital-plumbing (dedicated guide "How to Set Up Schema Markup for Personal Brand Site" is queued in Gaps & Tasks to Create — high priority)
- Related (run order): ensure-nap-consistency-across-platforms → claim-and-brand-facebook-page (and the other profile skills) → this
- Cross-links: /what-is-a-knowledge-panel (schema is the technical leg of a panel) · /personal-brand (Phase 1) · /entity-linking
