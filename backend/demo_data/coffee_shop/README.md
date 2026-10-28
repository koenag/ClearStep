# Juniper Coffee: inspectable fictional business records

Open `index.html` in a browser. On this Mac, from the repository root:

```bash
open backend/demo_data/coffee_shop/index.html
```

The preview includes sample POS rows, complete text records, links to each full file,
and the normalized input mapping. It does not run an analysis or call OpenAI.

## Business records

| File | What a business owner would recognize |
|---|---|
| `pos_sales_jul_sep.csv` | Checkout-level export: dates/times, repeated receipt IDs for multiple order lines, items, quantities, gross sales, discounts, net sales, collected tax and payment methods. No product costs. |
| `current_supplier_invoices.txt` | Readable text copies of three invoices: 5 lb bags, quantity/price, delivery, totals and payment terms. The text format is deliberate; no PDF/OCR capability is implied. |
| `alternative_supplier_quote_email.txt` | An offer email with price per bag/pound, minimum order, per-shipment delivery, payment terms and quote expiry. |
| `owner_stock_and_switch_notes.txt` | Informal stock counts and the owner's forward assumptions about usage, ordering, opening inventory, transition cost and operations. |
| `owner_event_plan.txt` | A rough budget and estimates for incremental attendance, spend, margin and repeats. These are forecasts, not historical event results. |

`analysis_settings.txt` is deliberately separate: horizon and sensitivity controls are
simulation settings, not information recovered from the POS or supplier invoices.

`manifest.json` is **developer/demo wiring**, not a business record. It transparently
maps the known fixtures to the existing financial fields, with exact source quotations
and observed/assumed labels. This edit does not implement general-purpose extraction.
The source records can be realistic while the mapping for this one fixture remains prepared.

## Reconciliation and limits

- July–September 2026: 11,478 sales lines, 8,297 distinct date/receipt pairs.
- Net sales after discounts, excluding tax: **$57,855.75**.
- COGS, contribution margin/profit, and net profit are **unknown** from this POS export.
- Coffee receipts: 100 lb in July, 110 lb in August, 90 lb in September. Total coffee
  purchases $3,600 plus three $40 deliveries = $3,720. This is procurement cash, not
  proof that all purchases were expensed as COGS during the period.
- Stock counts imply consumption including waste of 100, 105 and 95 lb; 100 lb/month
  is still labeled an assumption when used as a future forecast.
- Current price $12/lb, quote $10/lb, planned monthly deliveries $40/$50, one-off
  transition estimate $400. Model base result remains $1,880 over 12 months under the
  explicitly stated assumptions; it is not a guarantee about prices or operations.
- Event margin of 65% is an owner estimate, not a historical margin calculated from POS.

Both comparisons have complete numerical inputs. Some are explicitly estimates, and
risk review or clarification can still stop a live run. Completeness is not certainty.

## How the application uses this bundle

The next `live_demo.py` invocation seeds a **new versioned business** from these files.
Older businesses, facts, decisions and runs remain intact. Seeding is idempotent for
the same source/index fingerprint. Editing records creates a new fingerprint/business;
update the prepared mapping too if an indexed value changes. Missing evidence quotes
are rejected before a new business is written.

The live runner prints the preview path and writes `dataset_version` and `dataset_sha256`
into the run's `inputs.json`. That JSON contains the actual available facts for that run,
including any later user-confirmed changes stored for the same business. The static
preview's normalized table describes the initial fixture, not later clarification overrides.

For API usage, call `POST /api/demo/seed` and use the returned business ID for the new
records. A previously copied business ID still refers to its original data. To inspect
actual seeded source text, list `/api/businesses/{id}/sources`, then open
`GET /api/businesses/{id}/sources/{source_id}`; `chunks` includes the parsed content.

To regenerate these fictional records and the preview (no model call):

```bash
.venv/bin/python backend/scripts/build_demo_data.py
```

## Questions currently supported

1. **Coffee supplier switch:** current supplier versus the quoted alternative; purchasing
   cash costs, shipping, transition cost, MOQ inventory effects and sensitivity over a horizon.
   Example: “Would switching to Cedar Crest save money over 12 months?”
2. **One promotional event:** incremental visit/repeat contribution versus event/staffing
   budget under owner-supplied estimates. Example: “Would the Saturday tasting break even?”

The software has only these two model types. The current data describes this coffee
shop's bean purchase and event proposal. It does not generally resolve arbitrary
products/vendors, combine several decisions, forecast hiring, optimize pricing, model
loans, or answer broad profit-strategy questions with financial calculations. External
research is disabled. Unsupported or ambiguous queries can be rejected or need clarification.
