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

## Remaining boundaries

- This handles explicit account and gallery deletions. Failed upload/restore
  compensation and crash-between-upload-and-metadata reconciliation remain
  separate v1.0 work; this is not a universal orphan collector.
- Provider object versions, database snapshots and external backups need a
  separately agreed retention/deletion policy. Removing active objects does not
  prove erasure from historical backups or S3 version history.
- The table is currently an additive startup schema change, compatible with
  existing v0.7 databases. Versioned migrations and deployment rollback drills
  remain release gates.
- PostgreSQL CI exercises deletion during a simulated storage outage, verifies
  the task survives account removal and removes the real private test object
  after recovery. It is not proof of live Render/R2 operational readiness.
