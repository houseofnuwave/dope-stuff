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

## Outstanding release gates

- [ ] Observe real seller workflow and establish measurable value.
- [ ] PostgreSQL concurrency and state-transition fault tests; fix demonstrated races.
- [ ] Complete inventory, action-queue and sales pagination without silent omissions.
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
