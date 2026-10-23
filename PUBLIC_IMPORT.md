# Dope Stuff v0.7 public source import

Imported October 23, 2026 from the user-supplied `DopeStuff_v0.7_Source (9).zip`.
Archive SHA-256: `910248d972c280f9f4f093940db2a08f401baab621fb388ec2cc6b8279d1b83d`.
All 92 original manifest entries verified before publication.

The complete application, all original tests, operational tools, source documentation and deployment recipes are retained. UI copy, API display title and recovery messages use Dope Stuff. Historical documents and machine-facing identifiers retain FORM for v0.7 compatibility. The archive's original screenshots remain only in the supplied archive and are excluded from the public commit. The public SHA256 manifest describes the published files, excluding itself.

Reviewed the source inventory, environment templates, deployment examples, email/domain references, credentials and private-key patterns. No live credentials, populated environment files, private database or user photo storage were found in the source archive. Test passwords and isolated PostgreSQL/MinIO CI credentials are deliberate non-production fixtures. Expanded Git and Docker exclusions protect runtime state, credentials, exports and private storage. The original archive is unchanged.

Validation on Python 3.12:

- Original backend suite: **51 passed**, one dependency deprecation warning.
- Backend/tools byte compilation: passed.
- Frontend JavaScript syntax: passed.
- Local Chromium seller journey: blocked before browser launch by the macOS sandbox (`MachPortRendezvousServer: Permission denied`); no browser pass is claimed.
- GitHub Actions runs backend checks, the preserved desktop/mobile Chromium journey, and isolated PostgreSQL/MinIO integration checks. Check the actual run status before claiming these passed remotely.

No production deployment or live marketplace integration was performed. The archive contains no LICENSE; license choice is left to the repository owner, and public visibility alone grants no open-source license.
