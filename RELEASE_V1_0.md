# FORM Seller OS v1.0 — Founder Beta

**Version designation:** 1.0 means a cohesive, locally runnable *founder beta* for manually-assisted, multi-marketplace resale operations. It does NOT imply a hosted public paid SaaS or automatic cross-listing integrations. Release date: October 23, 2026.

## User experience that actually works

1. Create a private seller account, sign in, change password and revoke previously signed-in sessions.
2. Build a canonical inventory record (SKU, original images, verified condition, cost and price); edit, archive, preview CSV imports, export inventory, and duplicate an item into an independent draft without copying external records.
3. Use 7 advisory readiness checks, prepare marketplace-specific drafts, publish *manually* on each site and self-report publication/URL.
4. Record the sale and fees; other seller-reported live listings are placed in one prominent Action Center for **manual** removal, never auto-deleted.
5. See realized profit by marketplace with transaction-level and CSV exports, excluding taxes, refunds and subscription costs.
6. Export a comprehensive backup; inspect and restore it to a blank account of the same email; delete an account after password confirmation.
7. Use a calm editorial responsive interface with desktop and mobile seller journeys.

## New in this release versus v0.4

- Database-backed session revocation: changing the password increments session version, invalidating old signed cookies from other devices; legacy schema migrates automatically.
- Safe duplicate item draft (new server-generated SKU and no inherited photographs, sale, or active marketplace status).
- `/api/insights`: channel-level gross, fees, shipping, cost of goods, net profit and realized margin; available unsold inventory metrics.
- `/api/sales-export.csv`: transaction ledger for accounting, with spreadsheet-formula escaping.
- `/api/actions`: seller-scoped manual delisting queue for sold items, now presented prominently in the interface.
- Local status correctness: when all seller-confirmed live channels are marked removed, item returns to draft instead of misleadingly remaining active.
- Optional **loopback-only Docker Compose** for a repeatable local developer instance.
- Dedicated v1.0 security, launch and pilot test guides.

## Verified checks

- `PYTHONPATH=. pytest -q`: **31 passing integration/regression tests**.
- `node --check app/static/app.js`: passed.
- `FORM_CHROMIUM_PATH=/usr/bin/chromium python tools/ui_smoke.py`: desktop (1440px) and mobile (390px) test journeys passed with no page JavaScript exceptions and no horizontal layout overflow in tested views. These used Chromium and an in-process FastAPI bridge, not public HTTPS or real iOS Safari.
- See `docs/v10-desktop-action-center.png`, `docs/v10-mobile-action-center.png` and corresponding account screenshots.

## Current constraints — do not hide them from pilot users

- Not deployed. No public HTTPS address, production database, cloud disaster recovery, or email-based password reset.
- No connected API, automatic crossposting, automatic delisting, outside-message sync or real marketplace order detection. All platform statuses are seller-entered.
- No live Stripe billing/subscription enforcement. The on-screen subscription prices are research hypotheses, not paid plans.
- Single-quantity sales per item; cost/pricing inputs and recorded fees are seller-supplied. No refund/return accounting or tax handling.
- SQLite and file-based photographs are appropriate for **local** tests, not horizontally scaled infrastructure.
- Session- and IP-rate limits are in-process, not shared across replicas. Email verification and dedicated customer support are not implemented.
- Accessibility was improved but a full WCAG 2.2 AA audit is pending.
- The working name FORM has not been cleared for trademark/conflict use.

## Non-negotiable exit criteria for PUBLIC v1.0

Before inviting strangers to a paid hosted platform, complete the checked launch gates in `PUBLIC_LAUNCH_GATES.md`. The version number alone is not a commercial-readiness certification.
