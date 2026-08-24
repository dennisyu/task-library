---
name: create-wikidata-item-to-break-a-name-collision
description: Creates a Wikidata item for a client who shares a name with a more famous person, so search engines and AI models have a machine-readable handle that separates the two.
category: Personal Branding
stage: —
definitive_article: /personal-branding
status: complete
---

# Create a Wikidata item to break a name collision

**Use this when** a client is losing their own name in search or AI answers to a different person with the same or a near-identical name — especially when the other person has a Wikipedia article and the client does not.

Wikidata is the disambiguation layer that search engines and language models consult when they need to tell two people apart. If the other person has an item and your client does not, every engine has exactly one structured answer for that name, and it is not your client. Creating an item is free and takes about twenty minutes.

This is usually the cheapest single fix available for an entity collision, and it is almost always the one nobody has done.

## Inputs
- A Wikidata account (free; edits are immediate)
- The client verified identity facts: full name as published, occupation, employer or company, official website
- **Independently checkable anchors** — ISBNs, an Amazon author ID, a YouTube channel ID, a podcast ID, a registry number. Wikidata notability requires serious publicly available references; a personal website alone is not enough.
- The Q-ID of the person they are being confused with

## Steps
1. Search Wikidata for the client name first — `wbsearchentities` or the site search. Never create a duplicate. Record what you find, including every other person holding that name.
2. Identify the colliding entity and its Q-ID. Note exactly how the two names differ in print; a one-initial difference is a tighter collision than no difference at all, because it defeats the obvious fix of adding the initial.
3. Create the item with a precise label, a description that states occupation and affiliation, and aliases covering the shorter forms people actually search.
4. Add the identity statements: instance of human (Q5), sex or gender, country of citizenship, occupation, employer, official website.
5. Add every external identifier you verified — Amazon author ID (P4862), YouTube channel ID (P2397), X username (P2002), and any registry ID. These are what make the item checkable rather than assertive.
6. **Add `different from` (P1889) pointing at the colliding entity.** This is the property that does the actual disambiguation work. Everything else is context; this is the fix.
7. Create a linked item for the company if it has none, with `founded by` (P112) pointing back at the person, and `employer` (P108) on the person pointing at the company. A two-node graph is far more resilient than a lone item.
8. Record the new Q-IDs in the client notes and in the person `sameAs` schema on their website, so the site and Wikidata corroborate each other.

## Definition of done (QA checklist)
- [ ] Searched for duplicates before creating anything
- [ ] Item exists with label, description and aliases
- [ ] `instance of: human` present
- [ ] At least two independently checkable external identifiers attached
- [ ] **`different from` (P1889) points at the colliding entity**
- [ ] Company item exists and is linked in both directions
- [ ] Q-IDs recorded in the client notes and added to the site `sameAs` array

## Common failure modes
- **Creating a duplicate.** Always search first. Duplicates get merged by volunteers and you lose the edit history.
- **Skipping P1889.** An item without it just adds a third person with that name. It does not disambiguate anything.
- **Thin sourcing.** An item backed only by the client own website can be deleted for failing notability. Lead with ISBNs, registry numbers and platform IDs.
- **Editing the other person item.** Adding a reciprocal `different from` on their record is technically standard practice, but it modifies the public record of an uninvolved third party. Leave that to a human who chooses to make it.
- **Assuming this fixes the Knowledge Panel.** It is a prerequisite and a strong signal, not a switch. Measure before and after.

## Example(s)
Kim D. H. Butler, financial author, August 2026. Across ChatGPT, Gemini, Perplexity and Claude, the query "Who is Kim Butler?" surfaced **twelve distinct people**. The one leading on ChatGPT and Claude was Kim D. Butler, a Rutgers historian of the African diaspora — the only Kim Butler with a Wikipedia article, and holder of Wikidata item Q6408404.

The trap: the historian publishes as **Kim D. Butler** and the client signs **Kim D. H. Butler**. One initial apart, so adding the middle initial tightened the collision instead of breaking it. Three further Kim Butlers already held items (Q100981053, Q949208, Q75526302).

The client had no item at all. Two were created: **Q141162795** for the person, anchored on fifteen verified ISBNs plus Amazon author ID B00523N6HE and YouTube channel UCFwsvdeNpv09RmjQA1rLLuA, carrying `different from → Q6408404`; and **Q141162833** for Prosperity Thinkers, linked by `founded by` and `employer` in both directions.
