"""Inspect pending private-photo cleanup, or retry a bounded batch.

Run from the repository root using the app's same database/storage environment:
  python -m tools.photo_cleanup
  python -m tools.photo_cleanup --retry --limit 8

Never point this at a different storage location to clear an old queue. Restore
the original configuration to process its pending work. No secrets are printed.
"""
import argparse
import json

from app import db, photo_cleanup, photo_writes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retry', action='store_true')
    parser.add_argument('--limit', type=int, default=8, choices=range(1, 101))
    args = parser.parse_args()
    db.init_db()
    if args.retry:
        photo_cleanup.process_pending(limit=args.limit)
        photo_writes.reconcile(limit=args.limit)
    print(json.dumps({**photo_cleanup.status(), **photo_writes.status()}, sort_keys=True))


if __name__ == '__main__':
    main()
