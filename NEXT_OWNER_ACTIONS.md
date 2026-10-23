# Dope Stuff: next setup actions

1. Source is published at https://github.com/houseofnuwave/dope-stuff (public). Backend, desktop/mobile browser, and isolated PostgreSQL/private object-storage CI checks passed on commit `74a9bad4c5ff9b90b00da06e720324453fb9c5f3`. This verifies disposable test services, not a deployed Render/R2 environment.
2. Create a private Cloudflare R2 bucket with a bucket-scoped object API token; do **not** publish the bucket.
3. Connect the GitHub repository to Render using a new Blueprint, supply R2 secrets **inside Render only**, then run the checklist in `DEPLOY_STAGING_RENDER_R2.md`.

You do not need to buy a domain yet. Render provides an HTTPS staging address.

**Never send me passwords, tokens, secret keys, database URLs, bank details, or full customer records.** You can share a nonsecret repo URL and the public staging URL after initial deployment for review.

## v0.7 additions when you return

- Choose a sender domain and transactional email provider before enabling password reset on hosted staging. Avoid sharing credentials in chat.
- Test a reset message in a real inbox and verify old sessions are revoked. Until then, staged password recovery remains disabled by default.
- GitHub setup and disposable integration CI are complete. Configure Render/Cloudflare, then verify the deployed environment and backup/restore procedures before importing real inventory.
- Pilot with 3 original items; record real listing time and any manual-delisting errors.
