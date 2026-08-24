---
name: verify-ai-crawlers-can-fetch-the-site
description: Confirms GPTBot, ClaudeBot and PerplexityBot actually receive the real page rather than a JavaScript challenge stub, before any GEO, schema or llms.txt work is credited.
category: Website QA Audit
stage: —
definitive_article: /website-qa-audit
status: complete
---

# Verify AI crawlers can actually fetch the site

**Use this when** starting any GEO / AI-visibility engagement, and before crediting any schema, llms.txt or content work. A host-level bot challenge silently nullifies all of it, and the site looks perfect to every human who checks.

Managed hosts and security plugins (SiteGround anti-bot, Cloudflare Under Attack mode, Wordfence, Sucuri) intercept clients that do not execute JavaScript and return a small challenge stub, often carrying an `x-robots-tag: noindex` header. Browsers execute the challenge and pass. GPTBot, ClaudeBot, PerplexityBot and CCBot do not execute JavaScript, so they receive the stub instead of the page.

This is not a robots.txt problem. robots.txt can warmly welcome every AI crawler while the server never actually delivers it to one.

## Inputs
- The site public URL
- curl, or any HTTP client that does not run JavaScript
- Optional: a rendering crawler that can toggle JavaScript, for the control test

## Steps
1. Fetch the homepage with plain curl and record BOTH status and byte count:
   `curl -sS -o /dev/null -w "%{http_code} %{size_download}" https://example.com/`
2. Fetch `/robots.txt` the same way. A real robots.txt is plain text; a stub is usually under 1 KB of HTML.
3. Inspect response headers for `x-robots-tag`, `sg-captcha`, `cf-mitigated`, or a meta refresh to a challenge path.
4. Run the controlled test so you can prove WHAT is being discriminated against: fetch the same URL twice with a rendering crawler — once identifying as GPTBot, once as Chrome — with JavaScript disabled, then repeat with JavaScript enabled. If both user agents fail without JS and both succeed with JS, the discriminator is JavaScript execution, not identity.
5. If blocked, relax the bot challenge in the host security settings, or allowlist the AI crawler user agents. Do not simply lower the whole site security posture.
6. Re-test with step 1 and confirm a 200 with a full-size body. Record before and after byte counts.

## Definition of done (QA checklist)
- [ ] Plain curl on `/` returns 200 with full HTML, not a sub-1KB stub
- [ ] Plain curl on `/robots.txt` returns 200 and the real directives
- [ ] No `x-robots-tag: noindex` in the response headers
- [ ] Controlled test documented, naming the discriminator (JavaScript vs user agent)
- [ ] Before and after byte counts logged in the audit report

## Common failure modes
- **Reading only the status code.** The challenge frequently returns 202 or even 200, not 403. The byte count is the tell, not the status.
- **Testing in a browser.** A browser always passes. The test is meaningless unless JavaScript is off.
- **Trusting robots.txt or llms.txt.** Both can be perfect and both can be undeliverable.
- **Assuming the block is user-agent based.** Usually it is not. Allowlisting user agents will not help if the gate is JavaScript execution.
- **Crediting downstream work.** Schema, llms.txt and new articles are all worth zero until this passes. Sequence this task first.

## Example(s)
Prosperity Thinkers (prosperitythinkers.com), August 2026. Plain curl on the homepage and on robots.txt both returned **HTTP 202 with a 169-byte body** carrying `x-robots-tag: noindex` and a meta refresh to a SiteGround captcha path. The site had a clean robots.txt welcoming every AI crawler and a well-written llms.txt that those crawlers had almost certainly never received.

The controlled test settled the cause: same URL, same crawler, once as GPTBot and once as Chrome with JavaScript disabled — both got the 170-byte stub. With JavaScript enabled the same crawler received the real 265 KB page. The discriminator was JavaScript, not identity.

Two sister domains on the same host showed the same signature. The fix is a settings change of roughly thirty minutes, and every other recommendation in that audit was downstream of it.
