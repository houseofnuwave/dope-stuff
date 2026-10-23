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

The portable account-restore limit remains 500 items. Pagination does not change
that limit. Backup/export/restore bounds must be reconciled with lifetime catalog
size before v1.0; browsing large histories is not proof that they are recoverable.

## Remaining release gates

- [ ] Observe real seller workflow and establish measurable value.
- [ ] Finish PostgreSQL concurrency coverage beyond item sale/publication and fix demonstrated races.
- [x] Implement inventory, publishing, action-queue and sales pagination with boundary and browser tests.
- [ ] Reconcile portable restore bounds with complete lifetime inventory and sales history.
- [ ] Recover failed-upload/restore cleanup and reconcile interrupted writes.
- [ ] Versioned migrations, reproducible dependency lock, upgrade and rollback drills.
- [ ] Configure and verify real hosted HTTPS, PostgreSQL and private object storage.
- [ ] Verify database-plus-photo disaster recovery and recovery objectives.
- [ ] One-use invitations, mailbox verification, real email recovery and shared throttling.
- [ ] Operator alerts, support, retention/privacy and license decisions.
- [ ] Deployed HTTPS browser QA, including actual iPhone/Safari and keyboard accessibility.
- [ ] Five-seller pilot with observed activation, repeat work and support burden.

No v1.0 release, production deployment, commercial launch or paid provider setup
has been performed by this implementation pass.
