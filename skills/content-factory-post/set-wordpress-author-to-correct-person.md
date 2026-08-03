---
name: set-wordpress-author-to-correct-person
description: Make the site owner the byline on every post — not an admin account or VA — so Google attributes the content to the right entity and E-E-A-T accrues to the brand.
category: Content Factory — Post
stage: Post
definitive_article: GAP — to be written
status: needs-work
---

# Set WordPress author to correct person

**Use this when** a post is about to publish, or whenever an audit finds posts bylined to "admin," an agency login, or a VA instead of the site owner.

## Inputs
- WordPress admin access (ability to edit users and reassign post authors)
- The site owner's correct name, headshot, and short first-person bio
- List of recent posts and their current authors

## Steps
1. Confirm the site owner has their own WordPress user: display name is their real full name (never "admin"), profile photo/Gravatar is their real headshot, bio is first person and matches the bio used across their social profiles.
2. On the current draft, open the post's Author setting and set it to the site owner's account. VAs and agents draft under their own logins, but the published byline is always the owner.
3. Audit existing published posts: filter the post list by author and reassign anything bylined to admin, agency, or VA accounts to the owner.
4. Check the author archive page (`/author/<owner>/`) renders correctly and lists the owner's posts — this page is part of the entity's footprint.
5. Verify the byline shown on the live post template matches the owner's name, and that any author box links to their profiles consistently.
6. For personal-brand sites, confirm content reads in first person to match the byline (the /website-qa-audit Layer 2 standard).

## Definition of done (QA checklist)
- [ ] Current post's author = site owner; display name is the real full name, not a login handle
- [ ] Zero published posts remain bylined to admin/VA/agency accounts
- [ ] Owner's user profile has real headshot and first-person bio consistent with social profiles
- [ ] Author archive page renders and attributes correctly
- [ ] Linked back to the definitive article and relevant siblings
- [ ] Complies with Blog Posting Guidelines (if it publishes content)

## Example(s)
- Example needed — run the Meta-Article Prompt after first real run. Candidate: reassigning authorship on a personal-brand site (e.g., a Zach Peyton, Superior Fence & Rail article) from the posting VA to the owner.

## Run on a persistent agent (Fable 5)
A persistent agent (Fable 5, or comparable OpenAI/Google models) doesn't just fix the current draft — it sweeps the entire post list by author via the REST API, reassigns every admin/VA byline, and re-queries until the audit returns zero misattributed posts and every Definition-of-done box passes.
It stores the owner's canonical name, bio, and headshot reference in memory so every future run (and every other Post-stage skill) attributes to the same entity.
Each sweep is logged as a meta-article example so the library compounds.
See `boil-the-ocean.md` for the full operating principles.

## Definitive article & links
- Hub: GAP — to be written (interim grounding: /website-qa-audit "Verify WordPress author set to site owner name" and /blog-posting-guidelines)
- Related: /personal-brand · /what-is-a-knowledge-panel (entity attribution feeds the panel)
- Run order (Post stage): step-14b-run-linkwhisper-for-internal-links → **set-wordpress-author-to-correct-person** → place-content-on-seo-tree-with-proper-links
