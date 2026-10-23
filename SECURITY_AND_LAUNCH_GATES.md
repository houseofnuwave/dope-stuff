# Security, privacy and launch gates

**This repo is appropriate for local evaluation and an invitation-only private pilot on controlled infrastructure, not yet general public production or paid subscriptions.** The app is functional but has deliberate omissions. The software does not post or delist remotely, host paid subscriptions, send emails, or verify claimed item authenticity.

## Current protections (implemented)

- Passwords hashed with Argon2; signed session cookies; CSRF token required for mutations.
- Seller-owned item queries scoped by user id; image endpoints also owner-scoped.
- Seller-submitted text escaped in frontend template output; user-defined outbound URLs restricted to selected marketplace HTTPS domains.
- Rate limiting for anonymous registration/login/pilot-interest (in-process only).
- Parameterized SQL, foreign keys, unique per-user SKU, transaction-locked single-sale writes.
- Image dimension and bytes limits, re-encoding to WebP stripping embedded camera EXIF.
- CSV import size/row limits, atomic transaction and formula-safe CSV export.
- No sensitive external platform credentials stored or requested.

## Must pass before deploying public paid product

| Area | Pass requirement | Current |
|---|---|---|
| Identity | Verified email, account recovery, MFA for admin, account deletion | Not done |
| Sessions | Secure cookie over HTTPS, strong stable secret, session rotation, CSRF review | Partial |
| Hosting | HTTPS, firewall, safe env secrets, DDoS/rate limits, alerting | Not done |
| Persistence | Persistent DB, tested encrypted backups & restores, DB migrations | Partial / local |
| Privacy | Privacy notice, terms, data retention/deletion, consent, data export | Partial |
| Payments | Stripe Checkout, subscriptions, cancellations, idempotent verified webhooks | Not done |
| Support | Customer contact, ticket system, refund/cancellation policy | Not done |
| Testing | Browser E2E, mobile/screen reader QA, security pen test | Partial API tests |
| Marketplace permissions | Verify individual partner/API rights and supported actions | Assisted only |
| Observability | Structured logs, exception tracking, metrics, uptime alarms | Not done |
| Abuse | Shared rate limits, image scanning if required, report workflow | Not done |

## Mandatory deployment environment

Use a hosting provider that supports encrypted HTTPS, secure environment secrets, persistent volume or managed Postgres, static file service and daily backups. Store `FORM_SESSION_SECRET` as a long randomly generated value in secrets manager; set `FORM_COOKIE_SECURE=true` behind HTTPS. Do not publish SQLite DB or `data/photos/` as public assets. Do not host a public instance with default missing config or an ephemeral disk that will silently wipe sellers' records. For multiple replicas, migrate to Postgres and object storage.

## Marketplace policy and technical constraints

- [eBay Inventory API](https://developer.ebay.com/api-docs/sell/inventory/overview.html) supports authenticated inventory-related tasks with developer application credentials and permissions.
- [Depop Selling API](https://partnerapi.depop.com/api-docs/) states it is private and requires partner onboarding; OAuth for cross-listing software must be provisioned by Depop.
- [Shopify Admin GraphQL](https://shopify.dev/docs/api/admin-graphql/latest/mutations/productCreate) offers supported product mutations for properly authorized merchant apps; newly created products may be unpublished by default.
- Grailed, Facebook consumer Marketplace, Vinted and others require fresh policy and API verification, not assumptions from marketing pages or competitor claims.

Never implement automated form submissions, credential capture, anti-bot circumvention, scraping-based stock synchronization, undocumented endpoints or unofficial seller-login automation without an explicit compliance assessment and authorized access. Manual assistance must stay available when integrations are restricted.

## Data retention and customer trust

Define a retention schedule, data deletion workflow and export process prior to public launch. User photos and identity details should never be shared or used for machine learning without explicit permission. Keep opt-in marketing consent separate from core terms, avoid unnecessary data collection and give users access to their own data. Supply a support contact before taking outside users.

## Transparency standard

Never write **“synced,” “live listing confirmed,” “AI-authenticated,” “automatic delisting,” “verified sale,” “payment complete,”** or **“connected”** unless the specific feature actually performed the claimed operation and was verified. In the pilot UI, records are *seller-reported*, not marketplace sourced. The future plan table is a pricing hypothesis and billing is not yet enabled.
