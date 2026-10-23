# FORM v0.4 — Founder pilot checklist

After extracting the ZIP, run `bash start_mac.sh` and open http://127.0.0.1:8000. Use a private local machine. Run `PYTHONPATH=. python -m pytest -q` as a separate development check.

- [ ] Register using a new email and a strong password; sign out/in.
- [ ] Add a genuine item with 3+ original photos, title, SKU, brand (or Unbranded), size, observed condition, asking price, acquisition cost, and factual description.
- [ ] Confirm an item cannot be saved with the **Select actual condition** placeholder in the browser.
- [ ] In Publish studio, inspect the 7-part quality checklist. Fix any missing details; confirm the app does not claim to verify authenticity or publish remotely.
- [ ] Prepare a draft for Grailed or Depop; personally publish externally only if appropriate, then record the status in FORM.
- [ ] Record a sale on one channel and review the other seller-reported live listings in the manual delisting queue. Test the external delist process yourself.
- [ ] Visit Account, download full ZIP. Store it privately; it contains costs, private notes, and photographs.
- [ ] On a **disposable test account with no irreplaceable data**, test re-registering the same email into a blank local database and restore the ZIP. Verify cover photo, photos, description, sale history, and manual delist warnings.
- [ ] Confirm an incorrect password, invalid ZIP, foreign-account ZIP or attempt to merge into a non-empty account is rejected.
- [ ] Verify account deletion after saving a separate backup. Deleting local FORM records **does not** remove remote marketplace listings.
- [ ] Test at minimum Mac Safari and Chrome; then iPhone Safari on a local-network HTTPS test environment, not by exposing the development port to the public internet.
- [ ] Check 320px/390px mobile widths, keyboard-only form navigation, focus visibility and VoiceOver labels. The Chromium smoke test does not replace accessibility QA.

## Launch gates still missing

Production cloud database/storage, HTTPS, persistent server-side rate limiting, real email verification/password reset, abuse and security monitoring, privacy/terms/support documents, production backups and tested disaster recovery, audit of accessibility, official marketplace API permissions, and payments.

**The v0.4 software is not ready for paid public accounts.**
