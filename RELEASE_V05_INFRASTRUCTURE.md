# FORM Seller OS — v0.5 infrastructure milestone

**Basis:** The newer v1.0 Founder Beta code is preserved. "v0.5" identifies the **infrastructure workstream**, not a downgrade of the software or a claim that the service is publicly launched.

## Implemented and tested

1. Three lightweight health endpoints: `/livez` (process), `/readyz` (database schema + writable private image directory), `/healthz` (backward-compatible `{"status":"ok"}` with readiness check).
2. Fail-closed **hosted** configuration (`FORM_ENV=staging` or `production`): long stable signing secret, HTTPS-only cookies, explicit trusted host, matching HTTPS origin and absolute persistent data directory. TrustedHostMiddleware restricts inbound hostnames.
3. Content security policy and additional response security headers. HSTS only in hosted modes; local HTTP remains available.
4. Operator-grade **AES-256-GCM encrypted whole-app backups** including a consistent SQLite online snapshot and referenced image files, file-hash manifest, decryption authentication, SQLite integrity checks, safe extraction into a **new** recovery directory. Does not overwrite running data.
5. Single-instance `compose.staging.yaml` plus Caddy TLS proxy and a separate pilot access password (hashed for Caddy), with a persistent named volume and a healthcheck.
6. CI workflow to compile Python, parse the frontend JavaScript and run the backend test suite on commits.

## What is *not* done

- This package has **not** been deployed to your hosting account and DNS. No real domain or TLS certificate was tested. Docker Compose and Caddy were **not** run end-to-end here unless explicitly recorded elsewhere.
- This is **single-instance SQLite** infrastructure; not managed Postgres or distributed storage. No automatic offsite backup scheduler, database migration framework, or cloud restore drill with real customer data.
- No email password reset, verified invites, distributed rate limiting, billing, or authorized automated marketplace connectors.
- Caddy's shared pilot login restricts anonymous access to a private test deployment, but does not replace individual FORM accounts, email verification or strong per-user security controls.
- Backups contain seller data and password hashes **inside encryption**. The key must be stored separately; if it is lost, the backup cannot be recovered. Take routine off-host encrypted copies. Never put key and backup in the same location. Do not share the archive publicly.
- A database snapshot and filesystem photo copy are not globally locked together. During heavy concurrent photo changes, a backup may fail, rather than silently claim success. For critical recovery points, temporarily pause photo-changing traffic and retry.

## Local run and verification

```bash
python -m pip install -r requirements.txt pytest httpx
python -m pytest -q
node --check app/static/app.js
bash start_mac.sh
```

## Backup operation (on a trusted operator machine)

Set a secure 32-byte backup key as `FORM_BACKUP_KEY` (the command below prints a new one only once):

```bash
python -m tools.ops_backup keygen
# Add printed key to a secure password manager or secret vault.
# Export it to your *local shell* securely; do not commit it or paste it in chat.
python -m tools.ops_backup create --output /safe/offsite/FORM-2026-10-23.formbak
python -m tools.ops_backup verify --input /safe/offsite/FORM-2026-10-23.formbak
python -m tools.ops_backup rehearse --input /safe/offsite/FORM-2026-10-23.formbak --destination /private/empty-recovery-directory
```

The destination **must not already exist**. Recovery rehearsal produces `database/form.db` and `photos/` inside the new directory. Verify inventory and photos against source, then destroy temporary recovery plaintext securely and retain the encrypted backup separately. Do not use this command to overwrite a live instance.

For backups in a staging container, provide `FORM_BACKUP_KEY` only for the one backup command, output the encrypted file to a mounted private volume, transfer it to secure off-host storage and delete the staging copy. Test recovery on an isolated machine at least monthly. Operators must be responsible for retention/access policies.

## Private staging setup (requires your own domain and Linux server)

1. Place the source on a secured server running Docker + Compose. Configure a `stage.yourdomain.com` DNS record.
2. Generate a persistent session secret (48+ random bytes) and a **separate** long password for Caddy pilot access; generate Caddy's bcrypt hash using the documented command in `.env.staging.example`.
3. Provide the environment variables `FORM_STAGE_DOMAIN`, `FORM_SESSION_SECRET`, `FORM_PILOT_ACCESS_HASH` **through a secret manager or protected local environment file**. Do not commit that file. Protect any `.env.staging` file with mode `0600`.
4. Review the Caddyfile, DNS, firewall and upstream network configuration. Only expose HTTPS through Caddy; FORM itself is on an internal Compose network.
5. Run `docker compose -f compose.staging.yaml up --build -d`, then verify HTTPS, password gate, session cookies, host restrictions, registration, photos and backup restoration on an **isolated test instance**.
6. Schedule encrypted backups **off the server** and configure external uptime checks (without bypassing basic auth), database-disk usage alarms, log filtering and incident procedures.
7. Never enable commercial subscriptions or open public registration until the outstanding gates in `PUBLIC_LAUNCH_GATES.md` have been satisfied.

**Known limit:** The current in-process login rate limiter is not shared and may perceive all clients behind the reverse proxy as one IP. Keep the closed pilot small, and move throttling to a well-defined proxy/Redis solution before broader deployment.

## Pilot acceptance checklist

- Hosted environment refuses to boot with missing secret, insecure cookies or invalid host.
- Unauthorized public visitor is rejected by Caddy pilot gate.
- Seller A cannot see Seller B's photos, inventory, transaction data or portable ZIP.
- Create 3 items with 3–8 photos each; reload; confirm cover photos and SKU consistency.
- Record a sale with two manual marketplace statuses; Action Center must show the appropriate manual delist task.
- Take encrypted backup, verify, then **rehearse** recovery in a fresh isolated directory; reconcile row counts and photographs.
- Test sign-in and deletion via Chrome desktop, Safari on actual iPhone and keyboard-only navigation.

## Build priority after this milestone

1. Real deployment + monitored backups and a restore drill (external accounts and secrets required).
2. Postgres migration and private object storage with migration scripts and a real restore rehearsal.
3. Email verification/password reset, inviting a fixed pilot cohort, stronger abuse/rate limits.
4. Paid checkout only after piloting retention and operational reliability.
