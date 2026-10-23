# Next milestone · v0.4 — first hosted closed beta

**Goal:** one secure, hosted environment for 5 founder-invited sellers to test listing-to-sale workflows. Do not enable marketplace automation or billing as a shortcut.

## Sequence and exit conditions

1. **Production groundwork** — choose managed Postgres, private object storage, audited migrations, HTTPS staging URL, secure session/cookie config, cloud backups, restore test and server logs. Must not expose local SQLite/dev server to the internet.
2. **Authentication and privacy** — email verification, account recovery, shared per-IP/per-user rate limits, secret management, current privacy notice, account deletion verification on staging. Require appropriate controls for exporting potentially sensitive data.
3. **Product QA** — complete photo upload and cover change, manual publication, sale and manual delisting tests on actual desktop/mobile browsers; WCAG 2.2 AA audit, 320–1440px responsive check, loading/error/empty states and no silent failures.
4. **Pilot operations** — founder invite approvals, issue-reporting channel, operator backup/recovery runbook and a data retention/deletion policy. No marketing promises for unsupported integrations.
5. **Measurement** — instrument privacy-conscious events for listing completion, publishing time, manual delisting completion and seven-day repeat engagement. Obtain explicit consent for any nonessential analytics.
6. **Commercial validation** — ask five real sellers to create 10 real items, time work versus baseline and report errors. Decide whether premium $39.99/month is worth testing after retention evidence.

## Avoid

No scraped passwords, disguised marketplace bots, AI-authenticity claims, fabricated automatic syncing, premature Stripe checkout, or marketing statements inconsistent with shipped features. In particular, Vinted is not included in the assisted workflow.

## What the founder can provide later

- 3–10 genuine items (front/back/tag/flaw photos + correct brand, size, purchase price, target sale price).
- A test device/browser list (Mac/Safari, iPhone/Safari, Chrome) and honest feedback on each workflow.
- Hosting/billing account access only after choosing providers and storing credentials via secure secret management, not pasted into chat or committed to the repo.
