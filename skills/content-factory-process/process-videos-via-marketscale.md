---
name: process-videos-via-marketscale
description: Use the MarketScale platform to process and distribute raw video as an alternate Process-stage path, returning finished assets to the Content Library.
category: Content Factory — Process
stage: Process
definitive_article: /how-to-process-videos-via-marketscale
status: needs-work
---

# Process videos via MarketScale

**Use this when** a raw video is designated for the MarketScale processing/distribution path instead of (or alongside) the in-house Descript pipeline.

> **Evidence notice:** the live MarketScale SOP now documents the operating path. This skill is still `needs-work` until its instructions are reconciled against a current, privacy-safe run and that run has an inspectable reviewer receipt. A live article is documentation, not capability evidence.

## Inputs
- The raw video file from the Content Library `01-Raw` folder (already archived in Google Drive per Step 1 — Drive remains the system of record)
- MarketScale platform access (account credentials held by the brand, not an individual VA)
- The video's GCT statement, title, and description copy (so distribution carries correct framing)
- The Content Library tracker

## Steps
1. Confirm why this video routes through MarketScale rather than the standard Descript path (e.g., client mandate or distribution reach) and note the reason in the tracker — routing decisions are knowledge to capture.
2. Upload the raw video from Drive to MarketScale; never let MarketScale hold the only copy.
3. Submit it for MarketScale's processing (editing/captioning per the platform's workflow), supplying the GCT-derived title, description, and the brand/speaker attribution.
4. Review the processed cut before any distribution: names spelled correctly, captions accurate, nothing cut that changes the speaker's meaning. Apply the same authenticity bar as the Descript path.
5. Approve distribution targets in line with the video's Targeting — and record exactly where MarketScale publishes it.
6. Download the processed master and captions back into the Content Library (`02-In-Process` → `03-Published`), so the article pipeline (Steps 2–11) can still run off the same asset.
7. Update the tracker: processed-asset links, distribution URLs, and status. Embed/link distribution URLs from the eventual article where appropriate.
8. Document this run via `write-meta-article-documenting-agent-work`, link the receipt from the live MarketScale SOP, and propose any discrepancies as an SOP repair instead of silently diverging from the canonical page.

## Definition of done (QA checklist)
- [ ] Routing reason recorded; Drive still holds the master copy
- [ ] Processed cut reviewed and approved against transcript-accuracy and authenticity standards
- [ ] Distribution destinations recorded with URLs in the tracker
- [ ] Processed assets returned to the Content Library for the article pipeline
- [ ] Privacy-safe run receipt reviewed and linked from the live MarketScale SOP
- [ ] Linked back to the definitive article and relevant siblings

## Example(s)
- The live SOP contains worked interface examples and operating notes. A separate, privacy-safe end-to-end run receipt is still needed before this task can claim tested capability.

## Run on a persistent agent (Fable 5)

An agent may assemble routing notes, processing status, distribution URLs, and the draft receipt, but the named operator owns platform access, approval, publishing destinations, and final QA. Persistence and memory behavior remain E0 design intent until a frozen stack passes accepted trials. The agent should surface conflicts between a real run and the live SOP for review.
See `boil-the-ocean.md` for the full operating principles.

## Definitive article & links
- Exact task page: /how-to-process-videos-via-marketscale
- Related: /content-factory, /blog-posting-guidelines (the parallel in-house path), /meta-article-prompt-template
- Sibling skills, in run order: `step-1-upload-video-to-google-drive-and-descript` → this (alternate path) → `step-12-post-article-on-wordpress` (Post stage)
