---
name: how-to-process-videos-via-marketscale
description: "Compatibility record for auditing and maintaining the live MarketScale processing SOP; the canonical execution task is process-videos-via-marketscale."
category: Gaps & Tasks to Create
stage: —
definitive_article: /how-to-process-videos-via-marketscale
status: needs-work
---

# How to Process Videos via MarketScale

**Use this when** auditing the live MarketScale task page for drift. This legacy documentation-gap record is retained temporarily so old tracker references do not disappear; new execution work belongs to `process-videos-via-marketscale`.

> **Duplicate notice:** the missing article has been published. Do not count this compatibility record as a second independent task or evidence result. Merge it into the canonical execution task during the next tracker migration.

## Inputs
- Real MarketScale runs to document: how raw video goes in, what processing happens, what distribution comes out — the article documents the actual platform workflow, never invented features
- Every existing blitzmetrics.com article that mentions MarketScale or video processing/distribution
- The Content Factory Process-stage context: the existing lane is Google Drive + Descript (upload → transcribe → article, per /blog-posting-guidelines)
- WordPress access (Gutenberg) and the Nine Requirements checklist

## Steps
1. **Open the live task page** at `/how-to-process-videos-via-marketscale` and compare it with the canonical execution skill `process-videos-via-marketscale`.
2. **Write the definition** (first two paragraphs): what processing videos via MarketScale is — platform-based video processing and multi-platform distribution — what it is not, and when to use it versus the standard Descript lane.
3. **Document the complete process from real runs**: getting raw video into MarketScale; the processing workflow on the platform; the distribution outputs and which platforms they reach; how outputs hand back into the Content Factory (clips, transcripts, posts feeding the /blog-posting-guidelines pipeline); and the decision rule for routing a video to MarketScale versus Descript. Capture from actual operator runs — this is tribal knowledge being written down for the first time.
4. **Link every real example** of a MarketScale-processed video, each with a 1–2 sentence note on the outcome.
5. **Cross-link related definitive articles**: /content-factory (the pipeline this is a lane of) and /blog-posting-guidelines (the downstream steps).
6. **Add the course/service CTA** near the bottom.
7. **Set a short, memorable URL** redirecting to the hub — never to the homepage or a case study.
8. **Add an above-the-fold clickable diagram**: raw video → MarketScale processing → multi-platform distribution → Content Factory handoffs.
9. **Add E-E-A-T**: real distribution results and practitioner testimonials — highest authority first.
10. **Publish reviewed repairs** to the existing page; do not create a competing MarketScale hub.
11. Record the audit receipt, update the canonical execution skill where necessary, and queue removal of this duplicate record after tracker references migrate.

## Definition of done (QA checklist)
- [ ] Article meets all Nine Requirements, documented from real runs with no invented platform features
- [ ] The MarketScale-vs-Descript routing decision is stated concretely
- [ ] Existing task page repaired in place; no competing hub created
- [ ] Complies with Blog Posting Guidelines (title <60 chars, meta <160, keyword in first paragraph, no stock images, no AI-fluff)
- [ ] Audit receipt linked; canonical execution task updated where necessary
- [ ] Linked back to related hubs: /content-factory, /blog-posting-guidelines

## Example(s)
- The live task page is the documentation source. An independently reviewed, privacy-safe execution receipt is still needed for capability evidence.

## Run on a persistent agent (Fable 5)
An agent may compare the two documents, prepare a proposed diff, and assemble a receipt. A named reviewer owns access, factual accuracy, publication, and duplicate retirement. Claims about persistence or memory remain E0 until tested.
See `boil-the-ocean.md` for the full operating principles.

## Definitive article & links
- Exact task page: /how-to-process-videos-via-marketscale
- Related: /content-factory (Process stage) · /blog-posting-guidelines (the downstream pipeline) · how-to-grade-an-article-using-jennifer (the other Process-stage gap)
