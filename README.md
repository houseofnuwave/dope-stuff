# Dope Stuff — v0.7

Source recovered from `DopeStuff_v0.7_Source (9).zip`. Dope Stuff is the public product name; historical release notes below retain the former FORM name.

## Quick start

Requires Python 3.11+. Clone https://github.com/houseofnuwave/dope-stuff and run:

```sh
cd dope-stuff
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. Local data is created in `data/`; keep it private. For hosted configuration, follow the deployment documentation and supply real values through the host's secret manager. The `.env*.example` files contain placeholders; the app reads environment variables, not dotenv files automatically.

Run checks with `python -m pip install pytest httpx`, then `python -m pytest -q`. The included GitHub Actions workflow also checks JavaScript syntax and runs an isolated PostgreSQL/MinIO smoke test.

Compatibility: `FORM_*` environment variables, cookie/storage identifiers, generated SKU prefixes, export filenames and portable backup formats retain their v0.7 names so existing workflows and backups keep working. Visible interface text and recovery email branding use Dope Stuff. Historical screenshots are excluded from the public repository; application code has no dependency on them.

Licensing: no license was supplied in the source archive. No open-source license is granted by this import; the owner must choose a license before reuse permissions are offered.

The verification statements below are historical archive claims, not the results of this public import. See `PUBLIC_IMPORT.md` for current validation.

## Original v0.7 release notes

**Status:** 51 offline/backend tests and the full desktop/mobile Chromium pilot journey passed. **Not publicly deployed**, not a paid subscription service, and no authorized marketplace auto-posting. This release builds on every retained feature from v1.0 Founder Beta and the v0.5–v0.6 cloud infrastructure workstream.

**New v0.7 feature:** an expiring, single-use password recovery link. Email responses conceal whether an account exists. Reset tokens are stored only as SHA-256 digests, and a successful reset invalidates older sessions. Password changes revoke pending reset links. The frontend has a mobile-friendly recovery dialog. The offline/local dev mail spool is never permitted in hosted mode.

- To test on Mac: run `bash start_mac.sh`, open the site, create an account, sign out, choose **Forgot your password?**; the one-time reset message is saved with private permissions in `data/local-recovery-mail/` (not committed or archived in the source ZIP).
- To enable on HTTPS staging **after** obtaining an email provider: set `FORM_RECOVERY_MODE=smtp` and secure `FORM_SMTP_HOST`, `FORM_SMTP_PORT` (465 or 587), `FORM_SMTP_USERNAME`, `FORM_SMTP_PASSWORD`, and `FORM_SMTP_FROM`. Use the host secret manager, never a Git repo. Set `FORM_PUBLIC_ORIGIN` to the verified HTTPS service origin. Until configured, password recovery is **disabled in staging by default**, not faked.
- Test: `python -m pytest -q`; browser: `FORM_CHROMIUM_PATH=/usr/bin/chromium python tools/ui_smoke.py` (Chromium + Playwright required).

Read [`RELEASE_V07_RECOVERY.md`](RELEASE_V07_RECOVERY.md) for security and operational limitations and [`NEXT_OWNER_ACTIONS.md`](NEXT_OWNER_ACTIONS.md) for later cloud setup.

---

# FORM v0.6 — Cloud-Ready Candidate

**Primary handoff:** [`DEPLOY_STAGING_RENDER_R2.md`](DEPLOY_STAGING_RENDER_R2.md) and [`RELEASE_V06_CLOUD.md`](RELEASE_V06_CLOUD.md).

This release builds on the existing v1.0 Founder Beta and v0.5 operator-backup infrastructure. **It is not yet deployed to Render or verified against live PostgreSQL or Cloudflare R2.** The old SQLite/Caddy Compose recipe is now a *legacy local/single-host pilot path*; the new managed cloud path is `render.yaml`.

Local startup: `bash start_mac.sh` and visit `http://127.0.0.1:8000`.
Backend tests: `python -m pytest -q`. Chromium UI test: `FORM_CHROMIUM_PATH=/usr/bin/chromium python tools/ui_smoke.py`.

See original details below.

---

# FORM — Seller OS · v1.0 Founder Beta + v0.5 Infrastructure Milestone

**Status:** Working local, multi-user **v1.0 Founder Beta**, with an additional **v0.5 infrastructure workstream** (October 23, 2026). **Not:** a public-ready SaaS, marketplace auto-poster, automatic delister, or live billing product.

FORM (working name, not trademark-cleared) is an editorial, mobile-friendly operating system for independent fashion resellers. It stores item records, prepares channel-specific listing copy, tracks which sites the *seller confirms* they listed on, calculates actual recorded profit and flags places requiring manual delisting after a sale.


## v0.5 infrastructure workstream (new)

Start with [`RELEASE_V05_INFRASTRUCTURE.md`](RELEASE_V05_INFRASTRUCTURE.md). The new release adds verified encrypted operator backups (`python -m tools.ops_backup`), staging-mode configuration checks, liveness/readiness endpoints, a restricted Caddy HTTPS staging Compose example, and GitHub Actions CI. This is not a completed public deployment or a Postgres/cloud storage migration. The version label v0.5 refers to the infrastructure workstream; none of the v1.0 founder-beta features were removed.

**Verification:** 37 backend tests; in-process Chromium desktop/mobile seller journeys both pass; no real-domain TLS or container integration tests were performed.

## What actually works

- Account registration, login, secure password hashing, signed HTTP-only session, mutation CSRF protection
- Each seller can only access their own items, photographs, sales and channel records
- Create/edit/archive inventory items with SKU, condition, description, price, acquisition cost, quantity
- Multi-image photo galleries: up to 8 privately served images per item, re-encoded to WebP to strip camera EXIF/location metadata; removal, reordering and selectable cover photo
- Listing kit: editable-by-copy title and description, manual open-marketplace flow, publication checklist
- Manual publication status and optional verified-by-seller listing URL
- Record a single-quantity sale and calculate net profit = sale - fees - actual shipping - acquisition cost
- Flag previously self-reported live listings on other marketplaces for **manual** removal; confirm removal
- Search, filter, inventory CSV import/export (with mandatory preview and duplicate-SKU review in the UI), download blank CSV template, sales overview, account-separated records
- Portable private account ZIP download; restore-to-blank-account with preview, password confirmation, transactional record import and photo restoration; reauthenticated account deletion
- Password changes that revoke previously signed-in sessions, draft duplication without inherited external listings/sales/photos, and global Action Center for manual delisting
- Channel-level realized profit and margin analytics, sales CSV export (no predicted revenue)
- Public marketing homepage, working pilot interest capture, user feedback collection
- Advisory 7-point listing-readiness checklist. New items and condition-less CSVs default to Unspecified, not an unverified “New with tags”.
- Responsive premium desktop + mobile frontend, no asset CDN dependency

**Supported manual workspace names:** eBay, Grailed, Depop, Facebook Marketplace, Poshmark, Mercari, Vestiaire Collective, Shopify. These are **not connected integrations**. The tool does not publish, sync, read or delete anything on those platforms.

## Run locally

Requires Python 3.11+.

```bash
cd form-seller-os-mvp
python -m venv .venv
source .venv/bin/activate                   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -c "import secrets; print(secrets.token_urlsafe(48))"
# Store the generated secret in your terminal environment, never commit it:
export FORM_SESSION_SECRET='REPLACE_WITH_NEW_RANDOM_SECRET'
export FORM_COOKIE_SECURE=false            # local HTTP only
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. Create an account. Add a real item, prepare its listing, manually publish on a marketplace, mark it published in FORM, record a sale and review delisting actions. The database is created automatically in `./data/form.db`; files in `./data/photos/`. Existing v0.1 primary photographs are registered automatically into the v0.2 gallery without deleting their files.

**Mac shortcut:** Run `bash start_mac.sh` from the project folder (requires Python 3.11+). The launcher installs dependencies into `.venv`, creates a stable local-only session secret and opens the app in your browser. The `.form-local-secret` file must not be shared.

*Without FORM_SESSION_SECRET*: the local server generates a temporary secret. You will need to sign in again after restart. Explicitly set a stable secret for persistent sessions.

## Run tests

```bash
pip install pytest httpx
pytest -q
node --check app/static/app.js  # if Node is installed
```

The 31 API tests cover auth/CSRF, multi-tenant privacy, SKU collisions, photo re-encoding, CSV, marketplace URL restrictions, sales/delisting and pilot feedback. Tests use temporary SQLite databases, not your inventory.

## Seller workflow (honest by design)

1. Inventory > New listing, enter verified details and asking price; select 1–8 real garment photos.
2. Publish studio > select item > choose a channel.
3. Copy the generated draft, review facts, click the external marketplace link.
4. Publish manually *on that external site* and return to click “I published this myself.”
5. After a sale, Inventory > Sold > input sale price, fees and actual shipping.
6. Read the red manual delist queue and remove any live listings on the other platforms.
7. Confirm each external removal only **after** completing it yourself.

There are no scraping bots, browser credential collection, fake AI, synthetic purchase events or pretend “connected” statuses.

## Folder layout

```text
app/
  main.py                # FastAPI endpoints, validation, security, pilot workflow
  db.py                  # SQLite schema and connection helper
  static/index.html      # frontend shell
  static/styles.css      # design system + responsive layouts
  static/app.js          # front-end state, forms, views, API client
contracts-marketplace-adapter.ts  # future approved marketplace connector contract
sample_inventory.csv    # real-format import example; fictional goods only
tests/                   # API integration tests
WORK_MODE_MASTER_PROMPT.md
PILOT_PLAYBOOK.md
ENGINEERING_SPEC.md
SECURITY_AND_LAUNCH_GATES.md
```

## What blocks public / paid launch

This is an **operable closed-pilot prototype**, not a commercial production release. Before onboarding outside customers or taking payment, implement:

1. Public deployment with HTTPS, permanent encrypted backups, monitoring, error logging and tested restores.
2. Production session configuration, rate limiting stored in Redis, email verification, password reset, abuse monitoring, content security policy and CSRF/security penetration testing.
3. Terms of service, acceptable-use policy, privacy policy, retention/deletion process, customer support contact and documented opt-in for email communications.
4. Stripe-hosted subscription checkout + webhook signature verification, hosted billing portal, entitlement enforcement, tax considerations and cancellation behavior.
5. Automated browser/UX tests, mobile/accessibility QA, load testing, database migrations and cloud object storage.
6. For any real marketplace automation: obtain necessary API permissions, implement OAuth/token encryption/webhook idempotency and contract tests. Until then, keep assisted publishing explicitly labeled.

SQLite is suitable for local testing or a **single-instance** private pilot on persistent storage. Move to Postgres for multiple application instances / more concurrent users.

## v1.0 founder beta release

Read `RELEASE_V1_0.md`, `PUBLIC_LAUNCH_GATES.md` and `YOUR_FOUNDER_TEST_V1.md`. This is a **locally runnable** founder test release, not a subscription-ready production SaaS. A production-ready v1.0 requires meeting the launch gates independently of the version label.

The new Action Center lets sellers see all remaining manual delist tasks after recording a sale. Insights report only realized, self-entered transactions; password changes invalidate other sessions; duplicate produces independent drafts.

For optional loopback-only Docker usage, set `FORM_SESSION_SECRET` securely in your shell (e.g. `export FORM_SESSION_SECRET=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')`), then run `docker compose up --build` and open `http://127.0.0.1:8000`. This is for local evaluation only; it is not an internet-facing deployment recipe. To retain your existing inventory when upgrading, **make a full backup first** and follow the in-app restore process in a blank account with the same email, or back up the SQLite database and photo folder before copying files. Never upload secret files or unencrypted customer databases to source control.

## Work Mode handoff

1. Upload **`form-seller-os-mvp.zip`** to ChatGPT Work.
2. Paste the entire contents of **`WORK_MODE_MASTER_PROMPT.md`**.
3. Ask Work to inspect this repository and run tests before changing architecture.
4. Provide credentials only through approved secure connection/secret mechanisms, never in prompts or source files.
5. Review the launch gate checklist before letting Work deploy or enable checkout.

## Official API documentation to consult before integrations

- [eBay Sell Inventory API](https://developer.ebay.com/api-docs/sell/inventory/overview.html)
- [Depop private Selling API / partner onboarding](https://partnerapi.depop.com/api-docs/)
- [Shopify Admin GraphQL products](https://shopify.dev/docs/api/admin-graphql/latest/mutations/productCreate)

All third-party site names belong to their owners. No affiliation implied. Vinted is not included in assisted workspace due to commercial use and automation policy considerations.

## v0.2 pilot upgrade

- Multiple garment photographs per item with private authenticated viewing, automatic EXIF removal and a primary cover photo.
- One-click CSV template download; preview and fix errors before import. Import remains all-or-nothing.
- First-inventory guidance in the empty dashboard; responsive photo editor.
- 12 passing API tests; Node JavaScript parser check. Normal browser end-to-end verification was blocked by this execution environment and must be rerun on your computer before inviting outside sellers.
- For the next founder test, follow `YOUR_FIRST_10_ITEMS.md` and `RELEASE_V02.md`.

## v0.3 update — usable forms and data controls

A previously overlooked front-end modal click handler has been fixed; browser-mediated tests confirm the signup-to-listing workflow works on desktop and mobile. Use the new Account section to export your full local data ZIP and, if needed, delete your account with password confirmation. Item edit lets you make any gallery photo the cover.

See `RELEASE_V03.md` and `NEXT_BUILD_PLAN.md` for changes and pilot requirements. To run browser UI smoke tests after installing Playwright browsers, use `python tools/ui_smoke.py`. This test bridges a Chromium-rendered page to FastAPI's TestClient and does not verify public HTTPS hosting.

## v0.4 update — recovery and a more trustworthy listing flow

Go to **Account → Preview a backup** to inspect an existing FORM `form_account_backup.zip`. Enter your current account password and type `RESTORE MY DATA` to import to a **blank account with the same email**. The restore can recover your historical inventory, photographs and cover order, marketplace-status records, sales and feedback. It never accesses external marketplaces. There is no merge or overwrite in this pilot. Archives are limited to 128 MB compressed / 256 MB expanded and 500 inventory items.

Publish studio now displays a **7-part advisory completeness checklist** for the selected item. Verified condition must be chosen for new manual listings; if a source does not specify a condition, it is stored as **Unspecified** rather than falsely labeled new. The readiness checklist does not authenticate garments or guarantee factual accuracy.

Tests: **22 backend tests passed** and real Chromium UI journeys on desktop (1440px) and mobile (390px) passed through an in-process bridge, including multi-photo upload and ZIP restore. These checks do not establish live HTTPS deployment or device/browser accessibility conformity. See `RELEASE_V04.md`, `FIRST_PRINCIPLES_PRODUCT_STRATEGY.md` and `MANUAL_QA_CHECKLIST.md`.

**Important:** Account deletion is still irreversible *in the live workspace*. Restore is only possible from a previously downloaded backup into a new empty account with the same email. No external marketplace listing is changed automatically.
