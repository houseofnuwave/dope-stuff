# Private photo cleanup

Account and gallery-photo deletion now record cleanup work in `photo_deletions`
inside the transaction that removes the corresponding database records. Tasks
have no user ID or email and survive account deletion. Failed storage calls do
not discard tasks or store raw exception messages.

The API tries a bounded batch immediately. It returns 200 when the requested
active photo objects are removed, or 202 with `photo_cleanup_pending` when work
remains. Account sessions are cleared in either case; deleted inventory/photo
records cannot be accessed through the API. A pending response is not a claim
that every object has already been erased.

While the application runs, a worker checks the queue every 30 seconds and
attempts at most eight objects per batch. It stops a batch on a storage error
and rotates that task behind older attempts. Large accounts and storage outages
can therefore take multiple batches. Stopping the application pauses automatic
retries but does not delete queued work.

## Operator checks

From the repository root and the same database/storage environment as the app:

```sh
python -m tools.photo_cleanup
python -m tools.photo_cleanup --retry --limit 8
```

The first command reports counts; `--retry` performs a bounded batch of deletes.
It checks both explicit deletions and interrupted-write recovery, with a separate
bounded batch for each. It does not forcibly process a write whose grace/backoff
has not elapsed or whose registration transaction is still active.
Use these counts and the application's generic cleanup warnings in operational
monitoring. No external alert destination or deletion-time SLA is configured.

`other_storage_pending` means the configured local photo directory or S3
endpoint/bucket/prefix differs from the task's original location. Restore the
original environment to process those tasks. Never edit task target hashes to
force deletion against a new bucket. Rotating credentials for the same storage
location does not change the task target.

Retrying a completed storage delete is safe, including a crash before the queue
acknowledgment: storage deletion is idempotent and generated photo names are
never reused. Multiple workers may perform the same delete; only the successful
storage call permits removing the queue record.

## Interrupted uploads and restores

Before any provider write, `photo_write_intents` commits every generated name
and its original storage-target hash. It contains no user ID, email, credentials
or raw provider errors. Upload/restore then locks those intents throughout the
metadata transaction and storage calls. Successful registration removes intents
in the same commit as photo metadata. If intent persistence fails, no provider
write is attempted. A conflicting/nonblank restore checks its preconditions
before writing photos.

Same-owner content writes and account deletion serialize on the owner row in
PostgreSQL (SQLite uses its writer transaction). Deletion snapshots photo paths
only after acquiring this lock, so an in-flight registration cannot commit a
photo unseen by deletion. Storage calls deliberately occur while these locks
are held; a slow provider can delay that seller's mutations. This is a correctness
boundary, not a measured latency guarantee or a scalable asynchronous-upload design.

If a provider confirms a write but metadata rolls back, compensation transfers
the name to the normal deletion queue. If the write result is unknown, retain a
**cleanup watch** even after deletion succeeds: a timed-out provider may make
the original write visible later. Recovery repeats the delete with backoff
(30 seconds up to one hour). An app crash can leave a staging intent; after a
15-minute grace it becomes a cleanup watch. PostgreSQL recovery skips locked
active intents, while SQLite's writer lock excludes active registration. A
retired operation cannot resume a write. Recovery always checks both gallery and
legacy cover references before deleting, including an ambiguous commit result.

New operator counts distinguish `write_prepared`, `write_recovery_watch`,
`write_recovery_failed` and `write_other_storage`. A watch is **not** evidence an
object still exists, nor evidence that all provider copies have been erased.
Watches survive account deletion and process restart. They intentionally have
no automatic expiry: do not prune them just because an early delete succeeded.
Provider-specific quiescence verification, safe pruning, retention policy,
quota/budget alarms and a full historical orphan inventory remain operational
work. Heavy failure volumes can outgrow the default batch throughput. Monitor
growth and failures; no deletion completion-time SLA is promised.

## Remaining boundaries

- This covers newly tracked writes and explicit deletions, not untracked objects
  left by historical versions, arbitrary external bucket writes or a lost
  recovery database. It is not a universal orphan collector.
- Provider object versions, database snapshots and external backups need a
  separately agreed retention/deletion policy. Removing active objects does not
  prove erasure from historical backups or S3 version history.
- The table is currently an additive startup schema change, compatible with
  existing v0.7 databases. Versioned migrations and deployment rollback drills
  remain release gates.
- PostgreSQL CI exercises real private test objects with accepted-then-timeout
  writes, late visibility, active-write protection, competing restores and
  upload/account deletion on separate app event loops, plus deletion outage
  recovery. Inspect the actual candidate run before claiming it passed. This is
  not proof of live Render/R2 operational readiness or completed auth-race coverage.
