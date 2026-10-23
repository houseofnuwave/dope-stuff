# Dope Stuff v1.0 delivery evidence

Proposed release: a reliable hosted pilot for five invited sellers. This file
tracks current evidence, not the archive's historical “v1.0 Founder Beta” label.

## First implementation pass: deletion failures

Two fault-injection tests reproduced account/photo deletion failures in the
baseline: metadata was removed and a storage exception aborted the request,
without durable cleanup work. Added a persistent transaction-bound photo cleanup
queue, bounded immediate retries, a periodic worker, honest 202 pending responses,
an operator inspection/retry command and storage-location isolation.

Local backend validation: **58 tests passed** (51 preserved + seven new outage,
retry, transaction rollback, duplicate/crash and location-isolation tests).
Python compilation and frontend JavaScript syntax passed. A local Chromium run
timed out waiting for the initial registration button to stabilize; no local
browser pass is claimed for this change. The GitHub Linux browser and expanded
PostgreSQL/S3 outage tests must pass on the candidate commit before merge/release.

See `PHOTO_CLEANUP.md` for behavior, operations and remaining limitations.

## Second implementation pass: item state races

A deterministic interleaving probe reproduced publication overwriting a completed
sale: both API requests succeeded, leaving an item `active` with quantity zero and
an eBay channel still `manually_published`. The failure also exists with SQLite;
it is not merely a theoretical PostgreSQL concern.

Edit, archive and channel changes now check and update item state in an explicit
transaction. All item-state and gallery mutations take a PostgreSQL row lock
before checking their preconditions; SQLite retains its writer transaction lock.
Added an interleaving regression and simultaneous-sale check, reused by cloud CI
so the same invariants are exercised on real PostgreSQL.

Local validation: **60 tests passed**, including the original 51, seven cleanup
tests and two state-race checks. Python compilation and JavaScript syntax passed.
The preceding cleanup commit `a78d767f81948736e502aa30003924ecd75512d9`
passed its PostgreSQL/private-storage outage-recovery job. The new candidate still
requires its own complete CI result. Account-deletion versus concurrent writes,
restore concurrency and authentication races remain separate investigation work.

## Third implementation pass: reachable lists and honest totals

Inventory, publishing selection, manual-removal tasks and sales now have 50-row
pages with previous/next controls, ranges and full matching totals. Search and
filters reset paging; deleting the final task on a page clamps to the preceding
page. Older items can still be edited, prepared and selected even when outside
the current publishing page. Failed page requests keep the last good page;
out-of-order search responses cannot overwrite a newer result.

Sales counts and revenue charts use full-account aggregates, not the currently
visible page. Page count and row queries share a read snapshot so a concurrent
sale cannot produce an internally contradictory page. Separate page requests
remain live views: changes by another session can shift positions between pages.
Search and CSV export remain available for finding/exporting records.

Local validation: **71 backend tests passed**, including 11 new pagination,
owner-isolation, empty-page and concurrent-count checks. Clean desktop/mobile
Chromium journeys passed editing/publishing beyond 200 items, search races, a
simulated failed page request, clearing the sole task beyond 200 removals, and
paging through 703 sales with full totals. JavaScript syntax, Python compilation
and layout-overflow checks passed. Cloud CI also exercises old-cap boundaries
and count snapshots against PostgreSQL; verify the candidate's actual run before
claiming cloud validation.

At this milestone the portable account-restore limit still remained 500 items.
The fourth pass below addresses that mismatch; pagination alone did not establish
that larger histories were recoverable.

## Fourth implementation pass: successful exports must be recoverable

The two reproduced failures were a successful 501-item export rejected by its own
restore validator, and a successful photo-incomplete ZIP rejected on restore.
Export now uses a coherent database snapshot, requires every referenced photo,
checks shared record/byte budgets and validates the completed archive through the
actual restore validator before download headers. Missing/corrupt photos,
inconsistent records, storage outages and exceeded budgets fail explicitly.

The old 500-item ceiling is now 10,000 lifetime records, subject to the shared
128 MiB compressed / 256 MiB expanded / 10 MiB metadata / 4,000-photo budgets.
The first exceeded budget blocks portable export/restore; no records are silently
truncated. Large output spills to private temporary storage, photo reads are
bounded, and temporary handles close after success or failure. The UI uses the
backend limits and prevents JSON/HTML errors becoming misleading ZIP downloads.

Local validation: **90 backend tests passed**, including 19 new backup contract
tests, plus Python compilation and JavaScript syntax checks. Verification includes
a 501-item/500-sale/two-photo round-trip with complete
record comparison, a sale committed during export, every budget, partial photo
failure, temporary-file closure and sanitized storage errors. Clean local
desktop/mobile Chromium journeys downloaded and validated actual archives above
500 items and rejected missing-photo/HTML responses without a false download.
The cloud job now repeats large record/photo recovery against real disposable
PostgreSQL and private S3; verify its candidate result before claiming that pass.

See `BACKUP_RECOVERY.md` for the complete contract and limits. Portable archives
remain bounded; this does not replace full provider disaster recovery, immutable
object retention or multipart backup support for accounts exceeding those budgets.

## Fifth implementation pass: interrupted private-photo writes

Fault injection reproduced a provider accepting an upload and then returning a
timeout: the old route left one object, no photo metadata and no durable cleanup.
Uploads and restore staging now commit write intents before provider IO, lock
them through metadata registration, and transfer known rollback work to the
deletion queue. Unacknowledged/crashed writes retain cleanup watches that catch
late provider visibility even after an initial delete. Recovery protects live
gallery/cover references and cannot retire an active locked registration.

Same-owner content mutations, blank-account restore and account deletion now
share an owner-row lock on PostgreSQL. Account deletion acquires it before
snapshotting photos. Responses are constructed before releasing metadata locks,
avoiding a late response read that could trigger unsafe upload compensation.
Conflicting restores fail before storage writes. Authentication/token races
are not claimed solved by these content-operation locks.

Local verification: **114 backend tests passed**, including 24 new write-intent
checks, a real child-process crash, accepted-then-timeout and delayed visibility,
partial batches, cleanup/database outages, original-error preservation, commit
acknowledgement loss, target changes, active recovery locks, competing restores
and concurrent upload/account deletion on separate app event loops. Python
compilation and JavaScript syntax passed. Desktop/mobile Chromium seller and
large-backup/pagination journeys passed without script errors or horizontal
overflow. Cloud CI repeats the shared timeout, active-write, ambiguous-commit,
restore and deletion probes against disposable PostgreSQL/private S3; inspect
the candidate's actual run before claiming that evidence.

This is not an orphan inventory for historical untracked writes or proof of
provider quiescence. Cleanup-watch growth, operator alerting, safe pruning and
historical backup/version retention remain operational gates. Slow storage
holds that seller's content transaction; no latency/deletion-time SLA is claimed.
See `PHOTO_CLEANUP.md` for the protocol and operator counters.

## Sixth implementation pass: session revocation at the mutation boundary

A deterministic probe reproduced a request authorized before a password change
still committing an inventory item after revocation completed. Authenticated
mutations now carry an internal session-version snapshot and compare it again
after acquiring the owner lock. Revoked waiting writes fail with 401 before any
records or private storage are changed. Session API and backup public shapes
remain unchanged; internal authorization values are explicitly excluded.

Password changes verify/update the locked owner row. Recovery issuance and token
consumption use the same owner-before-token ordering as account deletion. A reset
token candidate is rechecked under that lock with expiry time measured after the
wait. Registration captures its own inserted principal in one transaction; login
verifies the locked current credential. This addresses the known revocation gap
and adds concurrency coverage, not a claim of complete authentication security.

See `AUTH_CONCURRENCY.md` for test scope, rollout ordering, revocation semantics
and limitations. Local tests include competing password changes, reset replay,
concurrent issuance, change/delete versus reset, recovery during deletion and
login versus change. Route-specific stale-request tests cover inventory, CSV,
channels, sales, gallery, feedback, account deletion and photo-bearing restore.
Cloud CI repeats the shared probes against disposable PostgreSQL; candidate
verification must come from its actual run, not the existence of these tests.

Local candidate validation: **137 backend tests passed**, including 23 new auth
checks. Python compilation, JavaScript syntax and clean desktop/mobile Chromium
seller, pagination and backup journeys also passed. Synthetic email capture is
not real SMTP delivery or mailbox-ownership verification.

## Seventh implementation pass: immutable atomic schema upgrades

The preceding probe reproduced partial schema persistence after a startup SQL
failure. Startup now uses three immutable SQL revisions and a checksummed ledger;
the complete pending batch, ledger entries and compatibility backfill commit or
roll back together. SQLite writer locking and a bounded PostgreSQL advisory-lock
transaction serialize upgraders. Changed/gapped/newer history and unsupported
core columns/keys/ownership relations fail closed. Migration application rejects
orphan SQLite rows and unvalidated PostgreSQL constraints instead of silently
deleting data or stamping a version. This is not exhaustive CHECK/default/trigger
or performance-index drift auditing.

Local/test startup retains automatic initialization. Staging/production startup
is now check-only and requires an explicit `python -m tools.migrate --apply`
maintenance step first; readiness verifies current schema history. The inspection
CLI is read-only and does not create a missing SQLite database. Docker includes
the operator tools and migration SQL. Staging templates/documents explicitly
require the maintenance sequence rather than implying automatic hosted setup.

Local validation: **160 backend tests passed**, including 23 new migration tests,
plus Python compilation, JavaScript syntax and clean desktop/mobile browser
journeys. Original v0.7 SQLite/PostgreSQL schema constants were recovered as inert
SQL fixtures, without executing archive code. Tests preserve all legacy records,
timestamps and existing cleanup work, restore cover associations, roll back
failed DDL, serialize two upgraders, survive a real child-process crash, reject
drift/unknown history and verify hosted check-only startup. An encrypted local
pre-upgrade recovery point restores into an isolated folder with complete record
and WebP-hash comparison after a simulated post-upgrade change. PostgreSQL CI adds
the shared original-schema, DDL-failure and competing-upgrade probes; verify the
actual candidate run before claiming it passed.

Publication review caught the private-data ignore rule matching `.sqlite.sql`
source names. Revision/fixture files now use packaging-safe underscore names;
their SQL bytes and ledger identities are unchanged. A regression check covers
the exclusion pattern. CI now also builds the actual Docker image and runs an
isolated real-HTTP cookie/CSRF, photo/export/deletion workflow and packaged
migration CLI. Docker is unavailable locally; only the candidate's actual CI
result can establish that container check, not the static filename test.

See `MIGRATIONS.md` for the operator protocol. No destructive down migration is
provided: old binaries must not erase/ignore privacy cleanup state. This local
data restoration rehearsal is not an old-release binary rollback, managed-provider
recovery or hosted cutover drill. Those and dependency locking remain release
gates. No real seller database or paid hosting environment was migrated.

## Remaining release gates

- [ ] Observe real seller workflow and establish measurable value.
- [ ] Finish PostgreSQL concurrency coverage beyond item sale/publication and fix demonstrated races.
- [x] Reject revoked in-flight content writes and establish owner-before-token authentication lock ordering with shared race probes.
- [x] Implement inventory, publishing, action-queue and sales pagination with boundary and browser tests.
- [x] Align portable export/restore validation, advertised budgets and larger lifetime-history recovery.
- [x] Recover newly tracked failed-upload/restore writes and reconcile process interruptions.
- [ ] Establish cleanup-watch monitoring/retention, provider quiescence/pruning and historical orphan inventory policy.
- [x] Versioned atomic schema migrations, original-schema upgrade/failure/concurrency probes and isolated local data restoration rehearsal.
- [ ] Reproducible dependency lock, full schema-drift review and actual release-image/hosted upgrade, rollback/cutover and provider recovery drills.
- [ ] Configure and verify real hosted HTTPS, PostgreSQL and private object storage.
- [ ] Verify database-plus-photo disaster recovery and recovery objectives.
- [ ] One-use invitations, mailbox verification, real email recovery and shared throttling.
- [ ] Operator alerts, support, retention/privacy and license decisions.
- [ ] Deployed HTTPS browser QA, including actual iPhone/Safari and keyboard accessibility.
- [ ] Five-seller pilot with observed activation, repeat work and support burden.

No v1.0 release, production deployment, commercial launch or paid provider setup
has been performed by this implementation pass.
