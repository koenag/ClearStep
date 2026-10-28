import io
import zipfile
from dataclasses import replace

import pytest
from app.config import DomainError
from app.data import parse_file
from openpyxl import Workbook
from pypdf import PdfWriter
from reportlab.pdfgen.canvas import Canvas

CSV = b"date,product,qty,price,cost,order_id\n2026-08-01,Latte,2,5,2,a\n2026-08-01,Cappuccino,3,4,1,a\nbad,Latte,-1,5,2,b\n"


def test_csv_baseline_and_invalid_rows(settings):
    r = parse_file("sales.csv", CSV, settings)
    b = r["baseline"]
    assert b["revenue"] == 22 and b["variable_costs"] == 7 and b["contribution_profit"] == 15
    assert b["units"] == 5 and b["transactions"] == 1
    assert "4" in r["warnings"][0]


def test_lines_not_transactions(settings):
    r = parse_file(
        "sales.csv",
        b"date,product,quantity,unit_price,unit_cost\n2026-08-01,Latte,10,5,2",
        settings,
    )
    assert r["baseline"]["transactions"] is None
    assert r["baseline"]["revenue"] == 50


def workbook(two=False, formula=False):
    book = Workbook()
    sheet = book.active
    sheet.title = "Sales"
    sheet.append(["date", "product", "quantity", "unit_price", "unit_cost"])
    sheet.append(["2026-08-01", "Latte", 2, "=2+3" if formula else 5, 2])
    if two:
        book.create_sheet("Other")
    out = io.BytesIO()
    book.save(out)
    book.close()
    return out.getvalue()


def test_xlsx_sheet_selection_and_formula_rejection(settings):
    assert parse_file("sales.xlsx", workbook(), settings)["baseline"]["revenue"] == 10
    with pytest.raises(DomainError, match="Select a sheet"):
        parse_file("sales.xlsx", workbook(two=True), settings)
    assert parse_file("sales.xlsx", workbook(two=True), settings, "Sales")["rows"] == 1
    with pytest.raises(DomainError, match="formulas"):
        parse_file("sales.xlsx", workbook(formula=True), settings)


def test_text_pdf_and_locations(settings):
    txt = parse_file("quote.txt", b"Price: $10\nShipping: $50", settings)
    assert txt["chunks"][0]["location"] == "lines 1-2"
    out = io.BytesIO()
    c = Canvas(out)
    c.drawString(70, 700, "Fictional supplier price: $10 per unit")
    c.save()
    pdf = parse_file("quote.pdf", out.getvalue(), settings)
    assert pdf["chunks"][0]["location"] == "page 1"
    assert "$10" in pdf["chunks"][0]["text"]
    assert pdf["baseline"] is None


def test_encrypted_and_scanned_pdf(settings):
    writer = PdfWriter()
    writer.add_blank_page(200, 200)
    out = io.BytesIO()
    writer.write(out)
    with pytest.raises(DomainError, match="OCR"):
        parse_file("scan.pdf", out.getvalue(), settings)
    writer.encrypt("secret")
    out = io.BytesIO()
    writer.write(out)
    with pytest.raises(DomainError, match="Encrypted"):
        parse_file("secret.pdf", out.getvalue(), settings)


@pytest.mark.parametrize(
    "filename,content",
    [
        ("bad.exe", b"abc"),
        ("bad.txt", b"\xff"),
        ("bad.pdf", b"not a pdf"),
    ],
)
def test_invalid_files(filename, content, settings):
    with pytest.raises(DomainError):
        parse_file(filename, content, settings)


def test_size_and_expanded_workbook_limits(settings):
    with pytest.raises(DomainError, match="limit"):
        parse_file("a.txt", b"x" * 30, replace(settings, max_upload_bytes=20))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/large.xml", "x" * 100000)
    with pytest.raises(DomainError, match="Expanded"):
        parse_file("a.xlsx", out.getvalue(), replace(settings, max_upload_bytes=1000))


def test_duplicate_headers_and_ambiguous_dates_are_not_guessed(settings):
    with pytest.raises(DomainError, match="Duplicate"):
        parse_file(
            "sales.csv",
            b"date,date,product,quantity,unit_price,unit_cost\n2026-08-01,2026-08-01,Latte,2,5,2",
            settings,
        )
    with pytest.raises(DomainError, match="Dates"):
        parse_file(
            "sales.csv",
            b"date,product,quantity,unit_price,unit_cost\n01/02/2026,Latte,2,5,2",
            settings,
        )


def test_pos_export_has_revenue_but_no_invented_costs(settings):
    content = (
        b"Date,Time,Receipt,Item,Qty,Gross Sales,Discount,Net Sales,Tax,Payment Method\n"
        b"2026-08-01,09:00,A,Latte,2,11.00,1.00,10.00,.75,Card\n"
        b"2026-08-01,09:00,A,Croissant,1,4.25,0,4.25,.32,Card\n"
        b"2026-08-01,09:05,B,Americano,1,3.75,.50,3.25,.24,Cash\n"
    )
    baseline = parse_file("pos.csv", content, settings)["baseline"]
    assert baseline["revenue"] == 17.50 and baseline["gross_sales"] == 19
    assert baseline["discounts"] == 1.50 and baseline["tax_collected"] == 1.31
    assert baseline["transactions"] == 2 and baseline["line_items"] == 3
    assert baseline["units"] == 4 and baseline["average_transaction_value"] == 8.75
    assert (
        baseline["variable_costs"]
        is baseline["contribution_profit"]
        is baseline["contribution_margin"]
        is None
    )
    assert all(p["cost"] is None for p in baseline["products"])


def test_generic_table_is_evidence_not_a_fake_sales_baseline(settings):
    result = parse_file(
        "purchase_register.csv",
        b"Supplier,Invoice total,Invoice date\nRoaster,1240,2026-07-01\n",
        settings,
    )
    assert result["baseline"] is None and result["rows"] == 1
    assert "no financial baseline" in result["warnings"][0]
