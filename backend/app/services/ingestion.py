import io
from decimal import Decimal

from app.financial.engine import money

ALIASES = {
    "sale_date": "date",
    "product_name": "product",
    "qty": "quantity",
    "price": "unit_price",
    "cost": "unit_cost",
    "transaction": "transaction_id",
    "order_id": "transaction_id",
}


def parse_csv(content: bytes):
    import csv
    from datetime import date, datetime

    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        names = reader.fieldnames or []
        normalized = [
            ALIASES.get(c.strip().lower().replace(" ", "_"), c.strip().lower().replace(" ", "_"))
            for c in names
        ]
        if len(set(normalized)) != len(normalized):
            raise ValueError("Duplicate normalized columns.")
        missing = {"date", "product", "quantity", "unit_price", "unit_cost"} - set(normalized)
        if missing:
            raise ValueError("Missing columns: " + ", ".join(sorted(missing)))
        records, invalid = [], []
        for raw in reader:
            try:
                if None in raw or any(raw.get(k) is None for k in names):
                    raise ValueError("Malformed row")
                row = {new: raw[old] for old, new in zip(names, normalized, strict=True)}
                # Require ISO dates: ambiguous slash-separated dates need explicit mapping.
                raw_date = row["date"].strip()
                if len(raw_date) == 10:
                    day = date.fromisoformat(raw_date).isoformat()
                else:
                    day = datetime.fromisoformat(raw_date).date().isoformat()
                nums = [Decimal(row[k]) for k in ["quantity", "unit_price", "unit_cost"]]
                if (
                    any(not n.is_finite() or n < 0 or n > Decimal("10000000") for n in nums)
                    or not row["product"].strip()
                ):
                    raise ValueError("Invalid value")
                records.append(
                    dict(
                        date=day,
                        product=row["product"].strip(),
                        quantity=str(nums[0]),
                        unit_price=str(nums[1]),
                        unit_cost=str(nums[2]),
                        transaction_id=row.get("transaction_id", "").strip(),
                    )
                )
            except (ValueError, ArithmeticError):
                invalid.append(reader.line_num)
        if not records:
            raise ValueError("No valid sales rows found. Dates must use YYYY-MM-DD.")
        warnings = (
            [
                f"Skipped {len(invalid)} invalid rows; ending CSV line numbers: {', '.join(map(str, invalid[:20]))}"
            ]
            if invalid
            else []
        )
        return records, warnings
    except (UnicodeError, csv.Error) as exc:
        raise ValueError("Cannot read CSV. Use a UTF-8 comma-separated file.") from exc


def aggregate(records):
    revenue = cost = units = Decimal(0)
    products = {}
    monthly = {}
    for r in records:
        q, p, c = map(Decimal, [r["quantity"], r["unit_price"], r["unit_cost"]])
        rev = q * p
        vc = q * c
        revenue += rev
        cost += vc
        units += q
        a = products.setdefault(
            r["product"],
            dict(
                product=r["product"],
                revenue=Decimal(0),
                cost=Decimal(0),
                units=Decimal(0),
            ),
        )
        a["revenue"] += rev
        a["cost"] += vc
        a["units"] += q
        month = r["date"][:7]
        monthly[month] = monthly.get(month, Decimal(0)) + rev
    tx = {r["transaction_id"] for r in records if r["transaction_id"]}
    transactions = len(tx) if all(r["transaction_id"] for r in records) else None
    dates = sorted(r["date"] for r in records)
    warnings = [
        "Sales data excludes fixed operating expenses; contribution profit is not net profit.",
        "Monthly figures reflect recorded dates only; incomplete periods are not extrapolated.",
    ]
    if transactions is None:
        warnings.append(
            "Transaction count unavailable: sales rows are line items, not unique transactions."
        )
    return dict(
        revenue=money(revenue),
        variable_costs=money(cost),
        contribution_profit=money(revenue - cost),
        contribution_margin=float((revenue - cost) / revenue) if revenue else 0,
        units=float(units),
        transactions=transactions,
        line_items=len(records),
        period_start=dates[0],
        period_end=dates[-1],
        products=[
            {
                k: (float(v) if k == "units" else money(v)) if isinstance(v, Decimal) else v
                for k, v in a.items()
            }
            for a in products.values()
        ],
        monthly=[dict(month=k, revenue=money(v)) for k, v in sorted(monthly.items())],
        warnings=warnings,
    )
