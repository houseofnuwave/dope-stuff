# Dope Stuff v2.0 — Seller Operations Advantage

**Status:** ACTIVE DEVELOPMENT GOAL. Not a release claim. Main stays on v1.0 until the hosted five-seller pilot and safety gates are proven.

## Product promise

An independent designer / vintage / streetwear reseller can document an item once, understand the economics of every offer, and know precisely which marketplaces require manual attention. Dope Stuff is the seller's business operating system; it is **not** a buyer marketplace and must not misrepresent supported marketplace integrations.

## Evidence-based success criteria

These are hypotheses and pilot targets, not established results:

1. **Listing efficiency:** median time to finish ten accurate garment drafts at least 30% lower than sellers' current baseline, without increased factual errors. Actual iPhone/Safari included.
2. **Retention and utility:** at least 4/5 invited pilot sellers return in week two; then test 10–20 pilot sellers before commercial release.
3. **Financial clarity:** sellers can reconcile at least five real sample payouts per channel with receipts; all estimated fee assumptions identified and dated.
4. **Inventory integrity:** zero confirmed unresolved app-caused lost items/photos, unauthorized cross-account access, or unflagged double-sale paths in rehearsed failure modes. Manual-only marketplace statuses must remain explicitly labeled.
5. **Recoverability:** independently restore matched database and photo snapshots, verify hashes, and practice operator cutover plus incident response with recorded timings and acceptable recovery objectives.
6. **Operational readiness:** tested access/revocation, deliverable email recovery, one-use invitations, observable cleanup queues, secure hosted HTTPS, and a hands-on keyboard/iPhone QA checklist.

## Sequenced engineering milestones

| Milestone | Goal | Gate |
|---|---|---|
| 0 — v1 stability | Review current PR #1 (photo operations), PR #2 (Offer Lab), PR #3 (Listing Studio); validate compatibility, correct defects, keep main safe | Green candidate tests; migration, access and recovery review |
| 1 — private deployment | Configure provider-backed PostgreSQL, private object storage, verified database/photo backups, TLS and invite-only accounts | Rehearsed provider restore; actual browser sign-in and iPhone Safari verification |
| 2 — first five sellers | Assisted onboarding; factual listings, pricing decisions, accurate manually confirmed channel statuses | Repeated usage and time-to-list measurements; zero unresolved P0/P1 incidents |
| 3 — smarter seller decisions | Inventory aging, stale listing checks, profit-floor calculators, reliable reminders and auditable seller actions | Cross-account safety and real seller adoption |
| 4 — authorized integrations | Adapter framework, idempotent remote intents, rate limit/outage handling, explicit seller consent, reconciliation | Provider API approval and live sandbox verification; never pretend sync works |
| 5 — v2 candidate | Harden, profile, price and ship only the validated top workflows | Release checklist and operational ownership approved |

## First v2 implementation increment: Inventory Aging

A read-only, per-seller inventory aging view using **date created inside Dope Stuff** (not original acquisition date or external marketplace listing date). It helps sellers identify unsold capital and re-review neglected inventory without inventing marketplace demand or automating price cuts. Counts and costs are full-account snapshots, not affected by a paginated page. Exclude sold/archived items and never leak other sellers' item records. Show an unambiguous definition.

## Red-team rules

- Never advertise an unconnected marketplace as synced; never scrape or impersonate marketplace sellers.
- Never insert an invented authenticity, size, material, condition or resale-value claim.
- Seller-entered costs are not authoritative tax/profit accounting.
- No production migration, paid provisioning, public deployment, merges or data deletion without explicit approval.
- A seller ZIP is **not** full managed-provider disaster recovery.
- Keep each change on a scoped draft PR, test actual candidate SHA and label external-hosting/device checks honestly.
- Read and reconcile the latest repository state before starting an increment to avoid duplicate work.

## Backlog, prioritized by proof of value

1. Finish and review safe integrations of current PRs.
2. Inventory aging / capital exposure and simple actions to revisit forgotten unsold items.
3. Mobile photo and description workflows under realistic bandwidth/low-storage conditions.
4. One-use invitation / secure recovery and recoverable hosted deployment.
5. Manually confirmed cross-channel reconciliation with stale-state visibility.
6. Authorized adapter / webhook sandbox tests only after API access confirmed.

**Business strategy:** Compete on seller efficiency and trust before considering an open buyer marketplace. Compare workflow outcomes against Grailed and existing reseller tools, not just the length of their feature lists.
