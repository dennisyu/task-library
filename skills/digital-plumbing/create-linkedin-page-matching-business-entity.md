---
name: create-linkedin-page-matching-business-entity
description: Set up a LinkedIn presence whose name and details exactly match the business entity, strengthening the entity graph Google reads.
category: Digital Plumbing
stage: —
definitive_article: /digital-plumbing
status: needs-work
---

# Create LinkedIn Page Matching Business Entity

**Use this when** the business has no LinkedIn page, the page name doesn't match the legal/brand entity, or the page is orphaned under a departed employee's profile.

## Inputs
- Owner's LinkedIn profile (company pages are administered through personal profiles)
- Canonical NAP record, logo, real cover image, and canonical bio/description copy
- Website URL

## Steps
1. Search LinkedIn for existing pages with the business name. Claim or consolidate strays — one entity, one page (a second competing page is entity vandalism).
2. Create (or take over) the Company Page with the name spelled exactly like the business entity in the canonical NAP. For a pure personal brand, the person's profile serves the role — same canon rules apply.
3. Make the owner a super admin. Operators get admin roles under them; remove ex-employees.
4. Complete the profile: logo as page photo, real cover image, website URL, industry, location matching the canonical address, and a first-person About section describing who the business serves.
5. Have current team members set the page as their employer so the page accrues real affiliation signals.
6. Verify the public page from a logged-out browser: name, location, and site link all match canon.
7. Add the LinkedIn URL to the schema sameAs list and website footer (sibling skills).

## Definition of done (QA checklist)
- [ ] Page name matches the business entity name character-for-character
- [ ] Owner is super admin; no orphan or duplicate pages remain
- [ ] Location and contact details match the canonical NAP; website link works
- [ ] Logo and cover are real brand assets; About written in first person
- [ ] LinkedIn URL present in schema sameAs
- [ ] Linked back to the definitive article and relevant siblings
- [ ] Complies with Blog Posting Guidelines (if it publishes content)

## Example(s)
- Example needed — run the Meta-Article Prompt after first real run.

## Run on a persistent agent (Fable 5)
A persistent agent (Claude Fable 5 or a comparable OpenAI/Google model) consolidates stray pages down to exactly one, sets the name character-for-character to the canon, and re-verifies the public page from a logged-out browser — looping until every Definition-of-done item passes, not 90%.
It self-checks admin roles and NAP details against that checklist, keeps the page URL in memory for the schema sameAs and footer runs that follow, and logs a meta-article example each run so the library compounds.
See `boil-the-ocean.md` for the full operating principles.

## Definitive article & links
- Hub: /digital-plumbing
- Related (run order): set-up-youtube-channel-with-proper-branding → this → set-up-consistent-headshots-and-bios-across-profiles → add-schema-markup-person-localbusiness
- Cross-links: /what-is-a-knowledge-panel (entity validation) · /personal-brand (Phase 1)
