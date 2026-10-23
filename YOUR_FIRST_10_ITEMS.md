# FORM — Test with your own first 10 pieces

**Your role:** Test the product as a reseller, not as a developer. We only need photographs and truthful product information; do not send passwords or marketplace login credentials.

## Recommended items
Choose ten actual items you own and can photograph: ideally 4 apparel pieces, 3 shoes, and 3 accessories (the mix is flexible). Avoid personal documents, buyers' addresses, or sensitive records in photographs.

## Minimum information per piece
1. Name/title, brand (if confirmed), category, size, color and condition.
2. Selling price and your actual acquisition cost.
3. Up to eight photographs: full front, back, brand tag, sizing label, close-up of fabric, any flaw, useful measurements, styled shot if you own the rights.
4. Description including defects and measurements you verified, not AI-invented details.
5. Where you intend to publish it.

## Start in the app (Mac)
1. Download the v0.2 ZIP, extract it, open Terminal in the `form-seller-os-mvp` folder.
2. Run `bash start_mac.sh`; open `http://127.0.0.1:8000`.
3. Create a private seller account in your local instance.
4. Add item 1 and its photographs with **New listing**.
5. Use **Publish studio** to prepare a manual listing for Depop or Grailed. Read carefully; publish there yourself only if ready.
6. Return to FORM to mark the channel manually published and add your actual external listing URL if desired.
7. Import the other 9 items using Inventory > Import CSV and **preview** before confirming, or enter them individually. Add photographs after import.
8. For a sold item, record price, platform fees and actual shipping; review manual delisting tasks. For test-only demos, use a clearly designated test item and never misstate real inventory as sold.

## Measure usefulness
- Time to create the first item; time to prepare its marketplace draft.
- Whether it was easy to add/replace photos on phone and computer.
- Missing data fields, confusing descriptions, incorrect profit assumptions.
- If you would use it weekly, and whether you would pay $14.99 / $39.99 / $89.99 monthly.

## Important constraints
No marketplace is connected. 'Published' means you verified publishing manually. Gallery uploads are stored on your local machine, not in cloud storage; back up your `data/` directory. This build is not ready for paid public customers.
