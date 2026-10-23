# Authentication and transaction ordering

## Reproduced failure

A synthetic authenticated inventory request paused after dependency authorization.
A different session changed the password and received success. Releasing the
first request still created inventory using the now-revoked cookie. A cookie
version check only at request entry did not protect a later database mutation.

## Current protocol

Authenticated content/account mutations carry an internal authorization-version
snapshot from `current_user`. `begin_owner_write` starts a write transaction,
locks the owner row, then compares that snapshot with the **current** database
version. Missing/deleted owners or missing/stale snapshots fail with 401 before
mutation or provider photo writes. This covers item creation/edit/duplication/
archive, channels, sales, CSV import, gallery changes, feedback, account deletion,
password change and backup restore. The snapshot is excluded from the session
API's public user object and portable backup account metadata.

PostgreSQL uses an explicit owner-row `FOR UPDATE` lock. SQLite uses its writer
transaction. Password changes verify the current credential under that lock,
increase the session version once, revoke existing reset links and commit before
issuing the replacement cookie. Registration captures its own inserted ID and
version in the creation transaction. Login verifies the locked current owner
row, then issues the cookie corresponding to that transaction's version.

All token writers take the owner lock **before** token locks. Recovery issuance
locks the owner selected by email before replacing links. Reset confirmation's
initial token lookup is only a candidate owner ID: after acquiring that owner's
lock, it rechecks and conditionally consumes the token using the time measured
after the lock wait. It changes the password/version and removes all that
owner's reset links in one transaction. Missing/deleted/expired/replaced/used
links receive the same 400 response. Account deletion follows the same owner-first
order, avoiding a token-first versus owner-first deadlock.

## Meaning of revocation

An already-running mutation that acquired the owner lock first may complete
before the password change/reset can commit. After revocation commits, a waiting
request authenticated with the old version cannot start its mutation. Revocation
does not retract bytes already delivered, cancel external requests or guarantee
termination of earlier read responses. Slow photo storage holds the seller's
content lock and can delay password changes/recovery; no latency SLA is claimed.

Do not mix old token-first and new owner-first app workers during a rollout.
Drain existing writes before replacing the process set. A verified hosted deploy/
rollback procedure and lock/timeout monitoring remain release work.

## Evidence and limits

The shared synthetic probes exercise concurrent password changes, reset replay,
competing issuance, reset versus password change/deletion, recovery during owner
deletion, login versus password change and revoked in-flight writes. Separate
ASGI event loops model different application workers rather than relying on
single-loop serialization. Local route-specific checks preserve all inventory,
channel, photo, sale and feedback records after revocation, including upload,
CSV, account deletion and restore. Expiry-after-wait and private-snapshot exclusion
are also tested.

The disposable PostgreSQL/private S3 CI job runs the shared probes; inspect the
actual candidate commit's run before claiming cloud verification. Test mail is
captured in memory, not delivered to real inboxes. Emails can arrive out of order;
only the latest **issued**, not necessarily latest received, reset link is valid.

This is not a complete authentication/security audit. Expiring one-use admission,
mailbox verification, real SMTP delivery/recovery, shared durable throttling,
trusted-proxy validation, operational alerting and deployed HTTPS/device testing
remain v1.0 gates. Process-local rate limits still do not survive restart or span
multiple app workers. No new external identity or paid provider is configured.
