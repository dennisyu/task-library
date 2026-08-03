---
name: claim-and-verify-knowledge-panel-when-it-appears
description: Claim and verify the Google Knowledge Panel as soon as Google generates one, putting the person in control of their own entity card.
category: Personal Branding
stage: —
definitive_article: /what-is-a-knowledge-panel
status: needs-work
---

# Claim and verify Knowledge Panel when it appears

**Use this when** monitoring during Phase 4 (Knowledge Panel) — and immediately when a panel first appears for the person's name.

## Inputs
- A monitoring routine: logged-out/incognito searches of the exact canonical name
- The person's own Google account (the one tied to Search Console / GBP)
- Live, accurate entity home, schema, and profiles — the panel is built from them

## Steps
1. Monitor weekly: search the exact canonical name logged out and in incognito; watch for a panel on the right rail (desktop) or top of results (mobile). Log the first sighting.
2. Do not wait passively — keep Phases 1–3 compounding. The panel appears when Google has enough consistent, validated entity signal; it cannot be requested into existence.
3. When the panel appears, use Google's "Claim this knowledge panel" flow, signed into the person's own Google account.
4. Complete Google's identity verification — the connected, verified profiles from Phase 1 are exactly what this step checks.
5. Once verified, suggest edits for accuracy: the canonical headshot, an accurate description, correct social links.
6. Fix facts at the source, not just on the panel: the panel mirrors the web, so correct the site, schema, and profiles first — then suggested edits stick.
7. Log the claim date and report it as the Phase 4 milestone; keep monitoring monthly for accuracy after the claim.

## Definition of done (QA checklist)
- [ ] Panel claimed and verified under the person's own Google account
- [ ] Photo, description, and links accurate; wrong facts corrected at their source
- [ ] Monthly accuracy monitoring continues post-claim
- [ ] Claim date logged and reported as the Phase 4 milestone
- [ ] Linked back to the definitive article and relevant siblings
- [ ] Complies with Blog Posting Guidelines (if it publishes content)

## Example(s)
- Example needed — run the Meta-Article Prompt after first real run.

## Run on a persistent agent (Fable 5)
This is the canonical persistent-agent task: a long-horizon agent (Claude Fable 5 or a comparable OpenAI/Google model) runs the weekly logged-out name search indefinitely, logs the first sighting, and drives the claim flow the moment a panel appears — looping until the Definition-of-done fully passes, not 90%.
It self-verifies panel facts against the canonical identity held in memory and fixes errors at their source — site, schema, profiles — rather than only suggesting edits.
The claim is the milestone the whole Plumbing → Content → Authority → Knowledge Panel chain in memory has been compounding toward; log it, keep monitoring monthly, and record a meta-article example each run so the brand compounds.
See `boil-the-ocean.md` for the full operating principles.

## Definitive article & links
- Hub: /what-is-a-knowledge-panel
- Related: /personal-brand · previous: implement-technical-schema-markup · next: measure-search-impressions-traffic-inbound-opportunities
