# FORM Seller OS — v0.7 Recovery and Account Trust

**Release date:** October 23, 2026. **Based on:** v0.6 Cloud-Ready Candidate plus retained v1.0 Founder Beta functionality.

## What actually shipped

1. SQLite and PostgreSQL `password_resets` table created on initialization; tokens never stored in plaintext in the database.
2. `/api/auth/recovery/request`: generic response for known/unknown addresses to reduce account enumeration; IP-limited in-memory requests (temporary pilot control).
3. `/api/auth/recovery/confirm`: 30-minute, single-use token; validates password; atomic token consumption and session-version increment to revoke existing login cookies. Only opaque fragment-based links are generated; no reset token appears in a JSON response or URL request path.
4. Existing authenticated password-change action now revokes pending recovery links.
5. Local development uses private `data/local-recovery-mail/` spool (files 0600, directory 0700). Hosted environments reject local spool. SMTP supports port 465 (SSL) or 587 (mandatory STARTTLS), credentialed, timeout-bounded, with platform-controlled HTTPS origin.
6. The login modal offers **Forgot your password?** on desktop/mobile; the reset link opens a secure modal, clears the token fragment from address bar, and logs the user out after completion.

## Verified now

- **51 automated backend tests**, including seven v0.7 recovery tests (non-enumeration, token hashes, expiration, replacement, single-use, invalidation after ordinary password change, legacy account sessions).
- Existing desktop and mobile Chromium workflows still pass, now extended through the recovery form and final login.
- Python compile and JavaScript syntax checks pass.
- No production email provider, managed Postgres instance, live Render URL, real R2 bucket, payment processor, or GitHub CI run was configured in this session.

## Operational and security boundaries

- **Do not enable publicly without a real SMTP sender, domain verification, deliverability tests, distributed rate limiting and abuse monitoring.** Email reset is disabled by default in hosted staging. Disabling recovery returns HTTP 503 for reset requests; it does not imply a message was delivered.
- In-process IP limiter is only a stopgap and can be bypassed across multiple web workers. Add shared Redis rate limiting, email-address throttling, audit monitoring and observability before public beta.
- Local recovery mail is for controlled development on your computer. It contains sensitive reset URLs; do not upload the `data` folder or copy it to source control.
- A response from the recovery request is deliberately generic even if sending email fails; server logs record a generic delivery failure without token/addresses. Alerting for real delivery failures is still needed.
- SQL schema initialization is not a substitute for production migrations under load; verify Postgres migrations against disposable and staging databases before customer data is stored.
- No email verification exists yet for new registrations. New signup flow should verify mailbox ownership before wider public access.
- The local Chromium browser test uses an in-process API bridge; it does not establish the behavior of a hosted TLS environment or real devices.

## Founder success criteria

1. Create a seller account, sign out, request password recovery, open the local recovery message, set a new password, and sign in using the new password.
2. Confirm the old password and previous sessions no longer work, and repeated reset-link use fails.
3. Create 3 real clothing listings and upload original photos to verify that inventory, descriptions, and the existing manual-delisting Action Center remain functional.
4. Move to Render/Postgres/R2 only after connecting services through the owner's secure accounts and completing real cloud smoke + backup recovery exercises.
