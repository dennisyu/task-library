---
name: ensure-nap-consistency-across-platforms
description: Make the business Name, Address, and Phone identical character-for-character across every platform so Google can trust the entity.
category: Digital Plumbing
stage: —
definitive_article: /digital-plumbing
status: needs-work
---

# Ensure NAP Consistency Across Platforms

**Use this when** the business name, address, or phone number appears in more than one variant anywhere online (suite vs. ste., LLC vs. no LLC, old phone numbers).

## Inputs
- Verified Google Business Profile (run verify-google-business-profile first)
- One canonical NAP record decided with the owner: exact name spelling, exact address format, one phone number in one format
- Login access to website, GBP, and all social profiles

## Steps
1. Write the canonical NAP with the owner and freeze it: one spelling of the name (with or without LLC — pick one), one address format (Suite vs. Ste — pick one), one phone format. Store it in the client record.
2. Inventory every surface that shows NAP: Google Business Profile, website footer, contact page, About page, schema markup, Facebook page, Instagram bio, YouTube About, LinkedIn page, email signatures, and any directory listings you control.
3. Compare each surface to the canon character-for-character. Log every mismatch — "St." vs "Street" is a mismatch.
4. Fix mismatches at the source, starting with GBP and the website (footer, contact page, and the JSON-LD schema must all match).
5. Update the social profiles next, then directories you can access.
6. Re-run the comparison after edits — platform review queues (GBP especially) can silently revert changes.

## Definition of done (QA checklist)
- [ ] Canonical NAP documented in the client record
- [ ] GBP, website footer, contact page, and schema markup show identical NAP, character-for-character
- [ ] Facebook, Instagram, YouTube, and LinkedIn show the same NAP (as much as each field allows)
- [ ] Zero known surfaces still showing an old phone number or name variant
- [ ] Linked back to the definitive article and relevant siblings
- [ ] Complies with Blog Posting Guidelines (if it publishes content)

## Example(s)
- Example needed — run the Meta-Article Prompt after first real run.

## Run on a persistent agent (Fable 5)
A persistent, max-effort agent (Claude Fable 5 or a comparable OpenAI/Google model) runs this as a diff loop: inventory every NAP surface, fix mismatches, then re-crawl days later to catch GBP review-queue reverts — repeating until every Definition-of-done box passes, not 90%.
It self-verifies character-for-character against that checklist, holds the frozen canonical NAP and surface inventory in memory so each run diffs against canon instead of starting over, and logs a meta-article example every run so the library compounds.
See `boil-the-ocean.md` for the full operating principles.

## Definitive article & links
- Hub: /digital-plumbing
- Related (run order): verify-google-business-profile → this → add-schema-markup-person-localbusiness (schema NAP must match) → set-up-consistent-headshots-and-bios-across-profiles
- Cross-links: /website-qa-audit · /what-is-a-knowledge-panel (entity consistency is the foundation of a panel)
