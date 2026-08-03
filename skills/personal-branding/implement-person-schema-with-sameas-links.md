---
name: implement-person-schema-with-sameas-links
description: Add Person schema JSON-LD to the entity home with a sameAs array binding every verified profile into one Google-readable entity.
category: Personal Branding
stage: —
definitive_article: /personal-brand
status: needs-work
---

# Implement Person schema with sameAs links

**Use this when** the entity home and all core profiles are live with consistent headshots and bios — the closing step of Phase 1 (Digital Plumbing).

## Inputs
- Live entity home at yourname.com
- Canonical name, job title, and the URL of the canonical headshot hosted on the domain
- The complete list of live profile URLs (LinkedIn, Facebook, Instagram, YouTube, Twitter/X, GBP if applicable)

## Steps
1. Assemble the facts: exact canonical name, url (https://yourname.com), image (headshot URL on the domain), jobTitle, and every live profile URL.
2. Write JSON-LD with @type Person containing name, url, image, jobTitle, and a sameAs array listing every verified profile — this is the wiring that tells Google all of these are the same person.
3. Install the JSON-LD so it renders on the entity home's homepage (site-wide header or homepage block; on WordPress, a schema-capable SEO plugin or a custom HTML block).
4. Validate with Google's Rich Results Test / schema validator until there are zero errors.
5. Spot-check the loop: every sameAs URL resolves to a live profile, and that profile's website field points back to yourname.com. One-way links are half a loop.
6. Make every schema claim match the visible site copy and published bios exactly — schema that contradicts the page is worse than no schema.
7. Set a standing rule: any new verified profile or profile-grade feature page gets appended to sameAs when it goes live.

## Definition of done (QA checklist)
- [ ] Person JSON-LD live on the entity home; validator returns zero errors
- [ ] sameAs lists every active profile; no dead or wrong-person URLs
- [ ] Every sameAs target links back to yourname.com (reciprocal loop verified)
- [ ] Schema facts identical to on-page copy and published bios
- [ ] Linked back to the definitive article and relevant siblings
- [ ] Complies with Blog Posting Guidelines (if it publishes content)

## Example(s)
- Example needed — run the Meta-Article Prompt after first real run.

## Run on a persistent agent (Fable 5)
A persistent agent (Claude Fable 5 or a comparable OpenAI/Google model) assembles the JSON-LD entirely from memory — canonical name, headshot URL, and the profile list saved by the earlier Plumbing runs — installs it, and loops validate → fix → revalidate until zero errors and every Definition-of-done box passes, not 90%.
It self-verifies the whole loop, not just the markup: every sameAs URL live, every profile linking back to yourname.com, every schema claim matching visible copy.
It stores the validated schema in memory as the entity baseline that Phase 4's technical-schema upgrade extends, and logs a meta-article example each run so the brand compounds.
See `boil-the-ocean.md` for the full operating principles.

## Definitive article & links
- Hub: /personal-brand
- Related: /digital-plumbing · /what-is-a-knowledge-panel · previous: add-consistent-headshots-and-bios-across-profiles · Phase 4 upgrade: implement-technical-schema-markup
