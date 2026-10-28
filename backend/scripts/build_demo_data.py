"""Rebuild the synthetic, human-readable coffee-shop fixture bundle. No model calls.

This is source-data authoring, not an alternate analysis/demo execution mode.
"""

import csv
import html
import io
import json
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

FOLDER = Path(__file__).resolve().parents[1] / "demo_data" / "coffee_shop"


def build():
    FOLDER.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)
    products = [
        ("Latte", Decimal("5.50")),
        ("Cappuccino", Decimal("5.00")),
        ("Americano", Decimal("3.75")),
        ("Cold brew", Decimal("5.25")),
        ("Croissant", Decimal("4.25")),
    ]
    sales = io.StringIO()
    writer = csv.writer(sales)
    writer.writerow(
        [
            "Date",
            "Time",
            "Receipt",
            "Item",
            "Qty",
            "Gross Sales",
            "Discount",
            "Net Sales",
            "Tax",
            "Payment Method",
        ]
    )
    for n in range(92):
        day = date(2026, 7, 1) + timedelta(days=n)
        orders = round((85 if day.weekday() < 5 else 105) * rng.uniform(0.85, 1.15))
        for order in range(1, orders + 1):
            receipt = f"JC-{day:%y%m%d}-{order:03d}"
            elapsed = ((order - 1) * 600) // orders + rng.randrange(max(1, 600 // orders))
            hour, minute = 7 + elapsed // 60, elapsed % 60
            payment = "Card" if rng.random() < 0.86 else "Cash"
            drink = products[rng.randrange(4)]
            basket = [drink]
            if rng.random() < 0.38:
                basket.append(products[4])
            for name, price in basket:
                quantity = 2 if rng.random() < 0.08 else 1
                gross = price * quantity
                discount = Decimal(".50") if rng.random() < 0.06 else Decimal(0)
                net = gross - discount
                # Fictional export tax, stored separately and excluded from revenue.
                tax = (net * Decimal(".075")).quantize(Decimal(".01"))
                writer.writerow(
                    [
                        day.isoformat(),
                        f"{hour:02d}:{minute:02d}",
                        receipt,
                        name,
                        quantity,
                        f"{gross:.2f}",
                        f"{discount:.2f}",
                        f"{net:.2f}",
                        f"{tax:.2f}",
                        payment,
                    ]
                )
    files = {"pos_sales_jul_sep.csv": sales.getvalue()}
    invoices = []
    for month, bags in [(7, 20), (8, 22), (9, 18)]:
        pounds = bags * 5
        goods = pounds * 12
        invoices.append(f"""RIVERBEND ROASTERS - FICTIONAL INVOICE
Invoice: RR-2026-{month:02d}-JC
Invoice / delivery date: 2026-{month:02d}-01
Bill to: Juniper Coffee

House Espresso, packed in 5 lb bags
Quantity: {bags} bags / {pounds} lb
Rate: $12.00 per lb ($60.00 per 5 lb bag)
Coffee subtotal: ${goods:,.2f}
Delivery - one shipment: $40.00
Tax shown on this fictional invoice: $0.00
TOTAL: ${goods + 40:,.2f}
Paid by bank transfer on 2026-{month:02d}-08.

Terms: minimum order 10 bags (50 lb). Delivery is charged per shipment,
not per bag. No subscription or fixed-term supply agreement.
""")
    files["current_supplier_invoices.txt"] = "\n--- next invoice ---\n\n".join(invoices)
    files["alternative_supplier_quote_email.txt"] = """From: sales@cedarcrest.example
To: owner@juniper.example
Date: 2026-10-15
Subject: House espresso wholesale quote for Juniper

Hi Maya,

Thanks for trying the samples. Our House Espresso is $50.00 for a 5 lb bag
(equivalent to $10.00 per lb). Your planned 20-bag order would be $1,000.00
for coffee. The minimum is 10 bags (50 lb).

Delivery is $50.00 per shipment at this order size, not per bag. With one
20-bag delivery the total is $1,050.00 before any applicable taxes.
We can schedule one consolidated delivery at the beginning of each month.
Payment is due within 14 days; there is no sign-up or account-opening fee.
This quote is valid through 2026-11-30. Prices beyond that date are not guaranteed.

Regards,
Cedar Crest wholesale team

[All names, domains, prices, and terms in this email are fictional.]
"""
    files[
        "owner_stock_and_switch_notes.txt"
    ] = """Juniper - owner's notebook, 2026-10-20 (FICTIONAL)

Bean counts, pounds of roasted coffee:
2026-06-30 closing stock: 20 lb
2026-07-31 closing stock: 20 lb
2026-08-31 closing stock: 25 lb
2026-09-30 closing stock: 20 lb
Invoices show 100 lb received in July, 110 lb in August, and 90 lb in September.
So use including waste was 100, 105, and 95 lb. About 6 lb over the three
months was spilled or used for dialling in; waste was not tracked daily.
Do not treat drinks sold as pounds of coffee purchased.

Planning assumptions, not historical measurements:
- Use 100 lb/month as the forward forecast, including normal waste.
- Place one consolidated bean order in each purchase month with either vendor.
- Begin the comparison after the remaining stock is used: assume zero opening
  stock for both alternatives. Do not expense today's remaining stock twice.
- Budget $400 one-off for staff tasting/training time and menu/label updates.
  This is my estimate, not a supplier fee or paid invoice.
- We have tasted the samples and will assume equivalent menu quality for the
  cost scenario. Equal reliability is an assumption, not verified performance.
- No cancellation fee applies to our current arrangement. Storage can hold
  200 lb; assume no additional storage cost at the planned quantities.
- Compare 12 months. Hold both prices flat for this first scenario, despite the
  new quote's expiry; show the price-change risk rather than call it guaranteed.

The POS export does not include milk, pastry, labour, rent, or recipe costs.
Neither net profit nor a measured shop-wide contribution margin is available.
"""
    files[
        "owner_event_plan.txt"
    ] = """Juniper Saturday tasting idea - owner's rough plan, 2026-10-21
FICTIONAL FORECAST ESTIMATES, not past event results.

Budget $500 for promotion, tasting materials and setup, plus $150 EXTRA staff
cost not included in the $500. Total event/staff budget is $650.

For a first scenario use 120 additional customer visits above our normal
Saturday trade, at $9 average spend per extra visit. We have not run this
kind of event before, so neither estimate is measured evidence.

Use 65% incremental contribution margin as a rough assumption. We don't have
complete recipe/ingredient costs in the POS export; do not present 65% as our
observed historical margin. Staff/event costs above must not be counted again.

Assume 20% of those incremental visitors return twice during the following
12 months. Repeat rate, repeat visits and their timing are unverified; don't
invent a monthly repeat-sales curve or claim causal attribution.
"""
    files["analysis_settings.txt"] = """DEMO ANALYSIS SETTINGS - NOT BUSINESS HISTORY
Forecast horizon: 12 months.
Current annual unit-price escalation: 0 (flat-price scenario assumption).
Proposed annual unit-price escalation: 0 (flat-price scenario assumption).
Supplier demand sensitivity: +/-20% around the forward forecast.
Proposed supplier price sensitivity: +/-5% around the quoted price.
Event attendance sensitivity: +/-25%.
Event spend sensitivity: +/-10%.
Event expense sensitivity: +/-10%.
Event repeat-rate sensitivity: +/-25%.
These are illustrative scenario controls, not estimated probability distributions.
"""
    facts = []

    def fact(kind, field, value, provenance, source, evidence, note=""):
        facts.append(
            dict(
                decision_type=kind,
                field=field,
                value=str(value),
                provenance=provenance,
                source=source,
                evidence=evidence,
                note=note,
            )
        )

    supplier = "supplier_switch"
    invoice = "current_supplier_invoices.txt"
    quote = "alternative_supplier_quote_email.txt"
    owner = "owner_stock_and_switch_notes.txt"
    settings = "analysis_settings.txt"
    fact(
        supplier,
        "current_unit_cost",
        12,
        "observed",
        invoice,
        "Rate: $12.00 per lb ($60.00 per 5 lb bag)",
        "One procurement unit is 1 lb roasted coffee.",
    )
    fact(
        supplier,
        "new_unit_cost",
        10,
        "observed",
        quote,
        "(equivalent to $10.00 per lb).",
        "Quoted price, not an observed future purchase; one unit is 1 lb.",
    )
    fact(
        supplier,
        "monthly_quantity",
        100,
        "assumed",
        owner,
        "Use 100 lb/month as the forward forecast, including normal waste.",
        "Forward quantity assumption, informed by stock counts; not inferred from cups sold.",
    )
    fact(
        supplier,
        "current_shipping",
        40,
        "observed",
        invoice,
        "Delivery - one shipment: $40.00",
        "USD per shipment; owner plans one shipment in each purchase month.",
    )
    fact(
        supplier,
        "new_shipping",
        50,
        "observed",
        quote,
        "Delivery is $50.00 per shipment at this order size, not per bag.",
        "USD per shipment; owner plans one shipment in each purchase month.",
    )
    fact(
        supplier,
        "switching_cost",
        400,
        "assumed",
        owner,
        "Budget $400 one-off for staff tasting/training time and menu/label updates.",
        "Owner estimate, not supplier fee.",
    )
    fact(supplier, "current_moq", 50, "observed", invoice, "minimum order 10 bags (50 lb).")
    fact(supplier, "new_moq", 50, "observed", quote, "The minimum is 10 bags (50 lb).")
    for field, value, evidence in [
        ("horizon", 12, "Forecast horizon: 12 months."),
        ("current_escalation", 0, "Current annual unit-price escalation: 0"),
        ("new_escalation", 0, "Proposed annual unit-price escalation: 0"),
        ("demand_variation", ".2", "Supplier demand sensitivity: +/-20%"),
        ("cost_variation", ".05", "Proposed supplier price sensitivity: +/-5%"),
    ]:
        fact(
            supplier,
            field,
            value,
            "assumed",
            settings,
            evidence,
            "Explicit simulation setting, not an observed business metric.",
        )
    event = "promotional_event"
    event_file = "owner_event_plan.txt"
    for field, value, evidence in [
        ("event_cost", 500, "Budget $500 for promotion, tasting materials and setup"),
        ("staffing_cost", 150, "$150 EXTRA staff"),
        ("incremental_visits", 120, "120 additional customer visits above our normal"),
        ("average_spend", 9, "$9 average spend per extra visit"),
        (
            "contribution_margin",
            ".65",
            "Use 65% incremental contribution margin as a rough assumption.",
        ),
        ("repeat_rate", ".2", "Assume 20% of those incremental visitors return twice"),
        ("repeat_visits", 2, "return twice during the following"),
    ]:
        fact(
            event,
            field,
            value,
            "assumed",
            event_file,
            evidence,
            "Owner forecast estimate; not a historical measurement.",
        )
    for field, value, evidence in [
        ("horizon", 12, "Forecast horizon: 12 months."),
        ("attendance_variation", ".25", "Event attendance sensitivity: +/-25%"),
        ("spend_variation", ".1", "Event spend sensitivity: +/-10%"),
        ("expense_variation", ".1", "Event expense sensitivity: +/-10%"),
        ("repeat_variation", ".25", "Event repeat-rate sensitivity: +/-25%"),
    ]:
        fact(event, field, value, "assumed", settings, evidence, "Explicit simulation setting.")
    files["manifest.json"] = (
        json.dumps(
            {
                "dataset_version": "coffee_shop_records_v1",
                "description": "Synthetic business records. The fact index below is demo wiring, not an owner-supplied document or a general extraction system.",
                "sources": list(files),
                "facts": facts,
            },
            indent=2,
        )
        + "\n"
    )
    for name, text in files.items():
        (FOLDER / name).write_text(text)
    write_preview(files, facts)


def write_preview(files, facts):
    sections = []
    for name, text in files.items():
        if name == "manifest.json":
            continue
        if name.endswith(".csv"):
            rows = list(csv.reader(io.StringIO(text)))
            table = (
                "<table><thead><tr>"
                + "".join("<th>" + html.escape(c) + "</th>" for c in rows[0])
                + "</tr></thead><tbody>"
            )
            table += (
                "".join(
                    "<tr>" + "".join("<td>" + html.escape(c) + "</td>" for c in r) + "</tr>"
                    for r in rows[1:21]
                )
                + "</tbody></table>"
            )
            body = f'<p>First 20 of {len(rows) - 1:,} sales line items. Full export is linked above. No unit costs or margin are included.</p><div class="scroll">{table}</div>'
        else:
            body = "<pre>" + html.escape(text) + "</pre>"
        sections.append(
            f'<section><h2>{html.escape(name)}</h2><a href="{name}">Open full source file</a>{body}</section>'
        )
    rows = "".join(
        "<tr>"
        + "".join(
            "<td>" + html.escape(str(f[k])) + "</td>"
            for k in ["decision_type", "field", "value", "provenance", "source", "note"]
        )
        + "</tr>"
        for f in facts
    )
    document = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Juniper Coffee: demo records</title><style>
body{font:15px/1.6 system-ui,sans-serif;margin:0;background:#f5f7f7;color:#243b36}main{max-width:1200px;margin:auto;padding:36px 24px}h1{font-size:30px;letter-spacing:-1px}h2{font-size:19px}section{background:white;padding:24px;border:1px solid #dce5e1;border-radius:10px;margin:24px 0}a{color:#08766b}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f7f9f8;padding:18px;font:13px/1.8 ui-monospace,monospace}.scroll{overflow:auto}table{border-collapse:collapse;font-size:12px;width:100%}th,td{padding:10px;border-bottom:1px solid #e5ece8;text-align:left;vertical-align:top}th{background:#edf5f1}.notice{background:#e8f2ec;padding:18px;border-radius:8px}.muted{color:#6b8075}
</style><main><h1>Juniper Coffee: inspect the demo data</h1><p class="notice"><strong>All records are fictional.</strong> Business records are separate from owner forecasts and simulation settings. POS revenue is observed within this synthetic dataset; product costs, shop-wide margin and net profit are unavailable.</p><p>These are readable text copies of invoices and an email, plus a POS-style CSV. No scanned receipts or PDFs are implied. The source fixtures below are what the current demo seeds. Existing historical runs keep their previous sources.</p>"""
    document += (
        "".join(sections)
        + f"""<section><h2>Normalized inputs used by this demo</h2><p>The seed explicitly maps these known fixtures into the existing model fields. This is a transparent fixture index, not proof of general document extraction. <a href="manifest.json">Inspect the complete mapping and evidence quotations.</a> In supplier calculations, one unit means one pound of roasted coffee.</p><div class="scroll"><table><thead><tr><th>Model</th><th>Field</th><th>Value</th><th>Provenance</th><th>Source</th><th>Interpretation</th></tr></thead><tbody>{rows}</tbody></table></div></section><section><h2>Currently supported questions</h2><p><strong>Supplier switching:</strong> compare the purchasing cash impact of the current supplier and one proposed supplier over a horizon. Example: “Would switching to Cedar Crest save money over 12 months?”</p><p><strong>Promotional event:</strong> simulate incremental contribution from one event, with explicit attendance, spending and repeat-visit assumptions. Example: “Would the Saturday tasting break even under the owner’s estimates?”</p><p>Hiring, pricing, loans, general profit strategy, autonomous research and arbitrary multi-decision forecasts are not modeled. Clarification or risk review can still stop a supported question.</p></section></main></html>"""
    )
    (FOLDER / "index.html").write_text(document)


if __name__ == "__main__":
    build()
    print(FOLDER / "index.html")
