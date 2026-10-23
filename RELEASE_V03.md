# FORM Seller OS · v0.3 · October 23, 2026

## Status

Local private-pilot build, **not** a production SaaS. No payment processing or live marketplace APIs. FORM prepares listing copy, tracks seller-confirmed publications and flags manual delisting.

## Changes since v0.2

- **Critical frontend bug corrected.** The modal backdrop's generic click handler formerly intercepted form submission clicks, preventing registration and inventory saving in the UI even though API tests passed. Interception now occurs only when the backdrop itself is clicked.
- **Cover-photo selection.** A seller can select any saved image as the cover while preserving all others. The server atomically verifies complete photo ownership and maintains photo order.
- **Portable full account backup.** Download private ZIP with JSON records and gallery photos; no password hash or secret is included. ZIP import/restore is not yet supported.
- **User-directed account deletion.** Requires the current password, explicit confirmation text and CSRF token. Deletes the seller's own local data and photos, then invalidates their session. Other sellers' data remains unaffected; external marketplace listings are NOT removed.
- **Account page and mobile navigation.** Account data controls are accessible from desktop sidebar and mobile More tab.
- **Security controls.** Deny framing, no-sniff, explicit API no-store caching, referrer and permissions policies; stricter name validation.
- **Accessibility improvements.** Associated labels on primary inputs, keyboard Tab focus handling inside modal, focused-element restoration after dismissal, motion preference support, explicit focus outlines.

## Verified

- **16/16 API integration tests pass** (`PYTHONPATH=. python -m pytest -q`).
- **JavaScript syntax passes** (`node --check app/static/app.js`).
- **Desktop/mobile browser UI smoke passes** using Chromium-rendered interface bridged to the in-process API: sign-up, create item, account page, zero uncaught JS errors or horizontal overflow for tested screens.
- Actual localhost navigation from Chromium was blocked in this execution environment. The in-process bridge does not verify HTTPS, cookies across real network origins, mobile device hardware, native file pickers, cloud backups or deployment.

## Non-goals and launch blockers

Do not charge customers or invite untrusted public traffic yet. Missing: public secure deployment, email verification and password recovery, production auth + distributed rate limits, persistent encrypted off-site backups with restore drills, monitoring, a privacy/terms/support program, Stripe billing, accessible UX audit across all journeys, data migrations and production object storage. No automatic publishing/delisting on marketplaces without explicit authorized integration.

## Founder test

1. On your Mac, unzip and run `bash start_mac.sh` inside the project directory.
2. Register a test account; add one genuine item with its actual condition, brand, SKU, price and cost.
3. Upload photos of front/back/tags/flaws and set a different cover photo.
4. Generate a Grailed or Depop draft; review all facts; post manually only if you intend to sell that item.
5. Confirm status back in FORM. Optionally record a genuine sale and complete any manual delisting tasks.
6. Download full account ZIP from Account; verify inventory and images are present.
7. Send issues using Feedback. Avoid using "Delete account" until you have a backup.

For development on macOS use `python -m pytest -q` after installing `pytest httpx` and optional browser smoke with `playwright` installed.
