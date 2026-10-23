# FORM Seller OS — public launch gates

This is a decision checklist, not an assertion that these requirements are done.

## A. Engineering and reliability

- [ ] Managed Postgres or equivalent data store, migrations, backups with restore rehearsals, tenant isolation policies and operational runbooks.
- [ ] Private cloud object storage with authorization, size limits, encrypted transport and retention handling.
- [ ] HTTPS staging and production, trusted-proxy configuration, secure cookie/session rotation, CSRF and CSP review, security headers, browser QA.
- [ ] Shared rate limits, abuse prevention, account email verification, password recovery, anti-enumeration behavior and session revocation assessment.
- [ ] CI tests, dependency scanning, security review, load/concurrency tests, exception tracking without personal data leaks.
- [ ] Full accessibility audit with keyboard/screen-reader testing, and Safari iPhone + desktop browser coverage.
- [ ] Uptime/error budgets, alerts, cloud billing limits and a tested incident response plan.

## B. Legal, trust and commerce

- [ ] Clear privacy policy, terms, data retention/deletion/support process and upload/content rights.
- [ ] Paid pricing validated using actual reseller interviews and prospective paid conversions.
- [ ] Stripe or other processor hosted billing, verified webhooks, robust entitlement checks, cancellation, refunds, taxes and invoice delivery.
- [ ] No unauthorized marketplace automation, password scraping, fake "sync connected" badges or false claims about partner API access.
- [ ] Trademark clearance for the final product name and insurance/legal review where appropriate.

## C. Founder pilot metrics

- [ ] At least 5 invite-only sellers each import or create 10 real items.
- [ ] Time to prepare one accurate listing measured against seller baseline (median reduction target ≥30%).
- [ ] No unknown loss of inventory, photographs, owner isolation, or data restore failure during pilot.
- [ ] All double-sale warnings verified with two or more self-reported live channels after a recorded sale.
- [ ] At least 60% of eligible pilot sellers use the product again within 7 days; interview churned pilot testers.
- [ ] At least 3 sellers state a clear dollar value they would pay, and test actual paid commitment only once infrastructure is safe.

## Next build order

1. Stage on managed hosting + Postgres/object storage with migration and disaster recovery.
2. Add recovery email + verification, deployment CI, telemetry/alerting (consent-appropriate).
3. Full founder real-inventory testing on Safari and Chrome.
4. Integrations ONLY where authorized and contractually supported.
5. Monetization after retention and trust are demonstrated.
