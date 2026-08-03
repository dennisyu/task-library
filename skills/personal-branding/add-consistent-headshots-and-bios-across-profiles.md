---
name: add-consistent-headshots-and-bios-across-profiles
description: Put the same professional headshot and the same bio facts on every profile so Google reconciles one person, not five.
category: Personal Branding
stage: —
definitive_article: /personal-brand
status: needs-work
---

# Add consistent headshots and bios across profiles

**Use this when** the core profiles exist but photos and bios differ by platform — Phase 1 (Digital Plumbing), immediately after profile setup.

## Inputs
- One current, professional headshot (real photo, same session/look, exportable per platform size)
- The canonical name string and the facts of the brand: what they do, for whom, and the proof
- The profile URL list from set-up-professional-social-profiles

## Steps
1. Select one headshot as canonical: real, current, well-lit, face recognizable at avatar size. Export crops for each platform from the same image.
2. Write the canonical bio once, in three lengths — one line, short (~50 words), long (~150 words) — same name spelling, same claims, same domain mention in each.
3. Use the exact canonical name everywhere; no nickname on one platform and full name on another. Name drift is the most common reason Google fails to reconcile the entity.
4. Apply the headshot and the right bio length to every property: LinkedIn, Facebook, Instagram, YouTube, Twitter/X, Google Business Profile (if applicable), the website About page, and any podcast or speaker profiles.
5. Verify each bio links or points to yourname.com wherever the platform allows.
6. Diff what you published against the website's About page — facts must match wherever they are reused.
7. Re-audit quarterly; when the headshot changes, replace it everywhere in one pass, never platform by platform over months.

## Definition of done (QA checklist)
- [ ] Same face, same name spelling, same bio facts on every live profile
- [ ] Every bio references or links to yourname.com where the platform allows
- [ ] Website About page matches the published bios
- [ ] Quarterly re-audit scheduled
- [ ] Linked back to the definitive article and relevant siblings
- [ ] Complies with Blog Posting Guidelines (if it publishes content)

## Example(s)
- Example needed — run the Meta-Article Prompt after first real run.

## Run on a persistent agent (Fable 5)
A persistent agent (Claude Fable 5 or a comparable OpenAI/Google model) sweeps every property on the profile-URL list held in memory, applies the canonical headshot and the three bio lengths, and loops until the Definition-of-done fully passes — same face, same spelling, same facts on every live profile — not 90%.
Self-verification is a diff pass: re-open each live profile and compare name, photo, and facts against the website About page.
It stores the canonical bio set and headshot reference in memory so the schema skill, podcast pitches, and press kits in later phases reuse them verbatim, and logs a meta-article example each run so the brand compounds.
See `boil-the-ocean.md` for the full operating principles.

## Definitive article & links
- Hub: /personal-brand
- Related: /what-is-a-knowledge-panel (entity identity depends on this) · previous: set-up-professional-social-profiles · next: implement-person-schema-with-sameas-links
