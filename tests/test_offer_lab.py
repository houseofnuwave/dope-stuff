"""The pure seller offer calculator has precise tier and input boundaries."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


def calculate(payload):
    if not NODE:
        pytest.skip("Node.js unavailable")
    code = ("const engine=require('./app/static/offer_lab.js');"
            "try { console.log(JSON.stringify(engine.estimate(JSON.parse(process.argv[1])))) } "
            "catch (e) { console.error(e.message); process.exit(2) }")
    result = subprocess.run([NODE, "-e", code, json.dumps(payload)],
                            capture_output=True, text=True, cwd=ROOT, timeout=5)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def basic(**overrides):
    return dict(saleCents=10000, costCents=4000, postageCents=0, buyerShippingCents=0,
                processingFixedCents=49, processingPercent="3.49",
                shippingMode="grailed_label", **overrides)


@pytest.mark.parametrize("sale,rate,commission", [
    (100, 6, 199), (3300, 6, 199), (11999, 6, 720), (12000, 9, 1080), (15000, 9, 1350)
])
def test_grailed_commission_threshold_and_minimum(sale, rate, commission):
    p = basic()
    p["saleCents"] = sale
    result = calculate(p)
    assert result["commissionRatePercent"] == rate
    assert result["commissionCents"] == commission


def test_processing_and_net_with_item_cost():
    result = calculate(basic())
    assert result["commissionCents"] == 600
    assert result["processingCents"] == 398
    assert result["sellerPayoutCents"] == 9002
    assert result["netProfitCents"] == 5002


def test_own_label_buyer_shipping_changes_commission_base():
    p = basic()
    p.update(saleCents=11500, buyerShippingCents=1000, postageCents=700, shippingMode="own_label")
    result = calculate(p)
    assert result["commissionRatePercent"] == 9
    assert result["commissionCents"] == 1125
    assert result["grossReceiptsCents"] == 12500
    assert result["netProfitCents"] == 12500-1125-485-700-4000


def test_grailed_label_does_not_add_buyer_shipping_to_seller_receipts():
    p = basic()
    p["buyerShippingCents"] = 500
    if not NODE:
        pytest.skip("Node.js unavailable")
    code = ("const e=require('./app/static/offer_lab.js');"
            "try{e.estimate(JSON.parse(process.argv[1]));process.exit(1)}"
            "catch(err){process.exit(0)}")
    result = subprocess.run([NODE, "-e", code, json.dumps(p)], cwd=ROOT, timeout=5)
    assert result.returncode == 0


def test_zero_profit_is_not_falsely_marked_as_loss():
    p = basic()
    p.update(costCents=9002)
    result = calculate(p)
    assert result["netProfitCents"] == 0
    assert result["isLoss"] is False
