# FORM Seller OS · v0.4 — Reliable restoration, not cosmetic complexity

**MVP pilot status:** local, not publicly hosted or billed.

## First principles

A reseller needs (1) a single trustworthy item record, (2) a dependable way to prepare marketplace listings without implying automation, (3) a reliable financial trail and (4) a way to recover their own records. Data loss is more damaging to customer lifetime value than adding speculative AI.

## Work in this release

- Advisory seven-point listing readiness in the publisher and listing kit; unverified condition defaults to `Unspecified` instead of `New with tags`.

- Restore a previously exported full account backup after a documented preview and reauthentication.
- Blank-account restore only. This intentionally refuses to overwrite or merge existing items.
- Restore item details, photos and their cover order, seller-confirmed marketplace status/URLs, completed sales and historical feedback.
- Reject mismatched accounts, foreign or missing photo references, traversal paths, duplicate ZIP entries, corrupt image data, oversized archives, invalid marketplace URLs, duplicate SKUs and inconsistent sale records.
- Stage photos with new random filenames; write database records in one SQLite transaction; roll back and remove staged photos on failure.
- A visual restore wizard in the Account area with explicit warning that restoring FORM records **does not restore or change external marketplace listings**.

## Still NOT implemented

This remains a local-only pilot. There is no hosting, managed Postgres, automated marketplace API, live payments, automated delisting, or email account recovery. A restored *manual marketplace status* remains a seller's past statement, not live verification.

## QA and usage

- Run `PYTHONPATH=. python -m pytest -q` from the extracted repository.
- For the owner restore flow: Account → Download backup ZIP; create a blank pilot account with the same email on a clean local database (or delete and re-register only after backing up); Account → Restore a backup → preview → password + typed confirmation → restore.
- Test with a handful of actual seller-owned garments and photographs. Keep a second offline copy of your backup.

**Security boundary:** ZIP restoration is limited to 128 MB compressed and 256 MB expanded, and to 500 inventory items during this pilot. Larger professional catalogs will need a streaming cloud implementation.
