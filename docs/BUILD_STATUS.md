# FORM Seller OS — Build status (October 23, 2026)

**Release:** v1.0 Founder Beta. Locally runnable, not hosted or merchant-production ready.

**API tests:** 31/31 passing (`PYTHONPATH=. pytest -q`).

**UI tests:** desktop 1440x900 and mobile 390x844 through Chromium with an in-process FastAPI TestClient bridge. Registration, item/photo upload, readiness, draft preparation, ZIP backup, account deletion, account restore, two reported live channels, recording sale, manual delisting Action Center, independent draft duplication, password change, no JavaScript exceptions and no horizontal overflow in tested views. Does not verify live Safari/Chrome, real domain HTTPS or operational recovery.

**Marketplaces:** assisted *manual* posting only. No OAuth credentials, partner API or automatic crosslisting.

**Billing:** no payments or entitlements. On-screen pricing represents a future hypothesis.

**Data storage:** SQLite and filesystem photographs, local evaluation only. Public hosting requires managed persistent storage, recovery/restore drills, and security rollout.

**Takeaway:** Complete enough for controlled on-device founder usability tests; not complete enough to advertise as an auto-crossposting SaaS or sell subscriptions.
