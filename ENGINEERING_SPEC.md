# Engineering specification · FORM Seller OS · v0.1

## Outcome

Help a solo fashion reseller manage 20–500 unique SKUs, reduce duplicate data entry, know where each item was manually posted, identify urgent delisting actions after sales, and understand actual profit. The north-star outcome is **weekly active sellers who complete a full item-to-sale workflow**, not merely created listings.

## Real implementation (this repo)

**Runtime:** Python FastAPI, Pydantic v2, argon2-cffi, Pillow, Starlette signed sessions; SQLite WAL for single-process trial; zero-build JavaScript and custom CSS for fast startup. Every persistence query that accesses a seller-owned item scopes to `user_id`. SQLite schema is defined in `app/db.py`.

**UI:** mobile-first, airy editorial cream/olive, serif editorial headings, sans-serif compact data tables, clear status color semantics, keyboard-friendly modals, no dark patterns. Avoid stock-photo-based fake listings or artificial purchase notifications. The preview values on the public landing are explicitly marked sample.

**Entity sketch:**

```
User (1) ── (*) Item (1) ── (*) ItemChannel
                |
                +── (0..1) Sale
User (1) ── (*) Feedback
PilotRequest (email, independent of account)
```

Item `status` is local `draft | active | sold | archived`. Channel status is `not_started | ready | manually_published | delist_required | delisted`. **Never equate self-reported `manually_published` with an API-verified status**.

**Canonical DB fields:**
- `items`: id, user_id, sku, title, brand, category, size, color, condition, description, notes, price_cents, cost_cents, shipping_cents, quantity, status, photo_path, timestamps.
- `item_channels`: item_id, channel, status, listing_url, updated_at.
- `sales`: item_id unique, user_id, channel, sold_cents, fee_cents, ship_cents, cost_cents, created_at.
- `feedback`: user_id, rating, message, timestamp.
- `pilot_requests`: email, source, timestamp.

Use **integer cents**; never store accounting money as floats. For hard currency edge cases, move to `Decimal` domain logic and explicit currency codes.

## API surface

| Method | Path | Purpose | Auth |
|---|---|---|---|
| GET | `/api/session` | Who am I / CSRF token | anonymous or signed-in |
| POST | `/api/auth/register`, `/api/auth/login` | create/sign in | anonymous |
| POST | `/api/auth/logout` | end session | CSRF |
| GET | `/api/overview` | inventory + finances + delist count | user |
| GET/POST | `/api/items` | list/search/create | user; POST CSRF |
| GET/PUT/DELETE | `/api/items/{id}` | get/edit/archive (not remote) | user; writes CSRF |
| POST/GET | `/api/items/{id}/photo` | upload/retrieve seller-only photo | user; POST CSRF |
| GET | `/api/channels` | manual channel definitions + URLs | user |
| GET | `/api/items/{id}/kit/{channel}` | generate factual draft | user |
| PUT | `/api/items/{id}/channels/{channel}` | seller confirmation | user + CSRF |
| POST | `/api/items/{id}/sale` | record once, enqueue manual delist | user + CSRF |
| GET | `/api/sales` | manually recorded sales | user |
| GET | `/api/export.csv` | safe CSV | user |
| POST | `/api/import.csv` | atomic 200-item CSV import | user + CSRF |
| POST | `/api/feedback` | usability feedback | user + CSRF |
| POST | `/api/pilot-request` | email capture, no billing | anonymous rate limited |

## Invariants

1. An item must always have exactly one owner. No cross-owner reads/writes or photo disclosures.
2. A SKU is unique within a seller, not across all sellers.
3. Recorded sale is single-shot. Double sale returns HTTP 409; don't silently overwrite financial history.
4. Sale changes local item to sold and flags all *other previously self-reported live* channels for removal. **It does not call any marketplace**.
5. Do not archive an item with self-reported live channels. Do not publish locally a sold item.
6. External listing URLs must be HTTPS and match the selected marketplace domain.
7. Image uploads are size- and dimension-limited, re-encoded, and served only to the owning account.
8. Duplicate SKU in an import rejects the entire import transaction.
9. Sales reports are based on actual seller-input numbers; no imaginary marketplace orders.
10. Never represent target-plan features as functional features.

## Known v0.1 limits / next technical work

- Single-quantity sale only. Add stock movements, partial fulfillment and returns before supporting quantity > 1.
- Client loads a maximum of 200 records per request. Implement server-side pagination, cursor/search sync and virtualized tables.
- SQLite single-node only. Add Postgres and Alembic migrations before horizontal scale.
- No email verification, reset or support tools. Add hosted auth provider before exposing a public signup at scale.
- Feedback and pilot interest are stored only; no transactional emails or CRM pipeline.
- No cloud photo storage, CDN, automated backups, billing, invoices or entitlements.
- Text generation is rule-based, **not AI**. Future AI must preserve original facts and ask for seller confirmation of material/brand/authenticity.
- No mobile app. Responsive web/PWA first; native only on evidence.
- No marketplace API integrations, sync or delisting. Add integrations only after formal API access and compliance review.
- No self-service account deletion, user export bundle or privacy portal. Required before public rollout.

## Adapter boundary for eventual approved integrations

Each adapter must declare static capabilities, never guess:

```ts
type Capability = 'publish' | 'edit' | 'delete' | 'orders' | 'inventory' | 'webhooks';
type ConnectionStatus = 'not_connected' | 'connected' | 'auth_expired' | 'unsupported';
type PublishResult =
  | { ok: true; platformListingId: string; publishedUrl?: string; verifiedAt: string }
  | { ok: false; code: 'NOT_AUTHORIZED' | 'RATE_LIMIT' | 'INVALID_LISTING' | 'RETRYABLE' | 'UNKNOWN'; message: string };
interface MarketplaceAdapter {
  id: string;
  capabilities: ReadonlySet<Capability>;
  connect(userId: string): Promise<ConnectionStatus>;
  publish?(sku: string, idempotencyKey: string): Promise<PublishResult>;
  delist?(platformListingId: string, idempotencyKey: string): Promise<PublishResult>;
}
```

Credentials must live server-side encrypted in a KMS-backed secret store; no marketplace passwords in our database. Webhooks need signature validation, idempotency, event deduplication, durable queues, and reconciliation audits. Cross-channel inventory updates should be **eventually consistent and observable**, never promised instantaneous without proof.

## Definition of done for next paid-pilot release

- Staging and production URLs with HTTPS, backup/restore drill, uptime alerts, error reporting.
- User account onboarding, email verification, reset, privacy/legal pages, support contact.
- Stripe *test-mode* subscription lifecycle, verified webhooks and entitlements; verify failed payment, cancel and retry flows.
- Three browsers (Chrome, Firefox, Safari), desktop and 390px mobile tested with keyboard and screen reader checks.
- At least 30 end-to-end scenarios for auth, item lifecycle, duplicate conflicts, file handling, sales, billing, privacy, and isolation.
- No known critical/high security issues. Pen test critical paths; logs do not contain passwords or tokens.
- Seller-facing capabilities plainly distinguish `manual`, `partner-approved API`, and `unavailable`.
- Pilot survey, seller activation funnel and opt-in analytics visible to founder with anonymization.
