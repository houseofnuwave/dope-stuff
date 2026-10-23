# FORM Seller OS v1.0 — Founder Quick Start

1. Extract the ZIP on your Mac. Keep the folder private because your future inventory/photos will be stored locally.
2. In Terminal, open the unzipped folder (`cd <path to the unzipped FORM_Seller_OS_v1_0 folder>`).
3. Run `bash start_mac.sh` (Python 3.11+ required). The local-only app opens at `http://127.0.0.1:8000`.
4. Create your seller account. Start with three genuine garments and work through `YOUR_FOUNDER_TEST_V1.md`.
5. Return to Account > Download full backup regularly. Do not store this unencrypted archive publicly.

To run automated tests from the project directory:

```
python3 -m pip install -r requirements.txt pytest httpx
PYTHONPATH=. python3 -m pytest -q
```

For browser smoke checks, install Playwright and Chromium first; see `tools/ui_smoke.py`.

**Upgrade from v0.4:** Export a full ZIP backup first, keep the old folder intact, then install v1.0 and create a new *empty* account with the same email to restore the archive. Alternative advanced migration: copy both the SQLite database and `data/photos` after stopping the old server, and back them up before starting the new version. The users table is migrated non-destructively with a session-version field on first launch.

**Warnings:** This is not an internet-facing server; do not forward its port or use public payment data. Marketplace statuses reflect only your confirmations and FORM will never auto-post or auto-delist. Pricing is conceptual, not live checkout.
