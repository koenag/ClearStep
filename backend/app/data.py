"""Deterministic parsing. No files or excerpts are sent to a model here."""

import io
import zipfile
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from pypdf import PdfReader

from app.config import DomainError
from app.services.ingestion import aggregate, parse_csv

SUPPORTED = {".csv", ".xlsx", ".txt", ".pdf"}


def parse_file(filename, content, settings, sheet=None):
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED:
        raise DomainError("unsupported_format", "Supported: CSV, XLSX, TXT, text-based PDF.", 415)
    if len(content) > settings.max_upload_bytes:
        raise DomainError("upload_too_large", "Upload exceeds the configured limit.", 413)
    if not content:
        raise DomainError("empty_file", "The file is empty.")
    try:
        if suffix == ".xlsx":
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                if sum(i.file_size for i in z.infolist()) > settings.max_upload_bytes * 20:
                    raise DomainError(
                        "expanded_file_too_large", "Expanded workbook exceeds the limit."
                    )
            book = load_workbook(io.BytesIO(content), read_only=True, data_only=False)
            try:
                names = book.sheetnames
                if sheet is None and len(names) != 1:
                    raise DomainError(
                        "sheet_required", "Select a sheet explicitly: " + ", ".join(names)
                    )
                chosen = sheet or names[0]
                if chosen not in names:
                    raise DomainError("invalid_sheet", "Selected sheet does not exist.")
                rows = []
                for row in book[chosen].iter_rows():
                    if len(rows) > settings.max_rows:
                        raise DomainError("too_many_rows", "Workbook exceeds row limit.")
                    if len(row) > 100:
                        raise DomainError("too_many_columns", "At most 100 columns are supported.")
                    if any(c.data_type == "f" for c in row):
                        raise DomainError(
                            "formula_review_required",
                            "Export calculated values: spreadsheet formulas are not evaluated.",
                        )
                    values = [
                        c.value.isoformat() if isinstance(c.value, (date, datetime)) else c.value
                        for c in row
                    ]
                    if any(v is not None for v in values):
                        rows.append(values)
                if not rows:
                    raise DomainError("empty_sheet", "Selected sheet is empty.")
                frame = pd.DataFrame(rows[1:], columns=[str(v or "") for v in rows[0]])
                content = frame.to_csv(index=False).encode()
                location = f"sheet {chosen}"
            finally:
                book.close()
        else:
            location = "CSV"
        if suffix in {".csv", ".xlsx"}:
            # Bound dimensions before row-by-row financial validation.
            frame = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False)
            if len(frame) > settings.max_rows or len(frame.columns) > 100:
                raise DomainError("table_too_large", "Table exceeds row/column limits.")
            records, warnings = parse_csv(content)
            baseline = aggregate(records)
            return {
                "format": suffix[1:],
                "chunks": [{"location": location, "text": content.decode("utf-8-sig")}],
                "baseline": baseline,
                "warnings": warnings,
                "rows": len(records),
                "columns": list(frame.columns),
            }
        if suffix == ".txt":
            text = content.decode("utf-8-sig")
            chunks = [
                {
                    "location": f"lines {i + 1}-{min(i + 60, len(text.splitlines()))}",
                    "text": "\n".join(text.splitlines()[i : i + 60]),
                }
                for i in range(0, len(text.splitlines()), 60)
            ]
        else:
            pdf = PdfReader(io.BytesIO(content))
            if pdf.is_encrypted:
                raise DomainError("encrypted_pdf", "Encrypted PDFs are unsupported.")
            if len(pdf.pages) > settings.max_pdf_pages:
                raise DomainError("too_many_pages", "PDF exceeds page limit.")
            chunks = [
                {"location": f"page {i + 1}", "text": page.extract_text() or ""}
                for i, page in enumerate(pdf.pages)
            ]
        length = sum(len(c["text"]) for c in chunks)
        if length > settings.max_document_chars:
            raise DomainError("document_too_large", "Extracted document exceeds text limit.")
        if not any(c["text"].strip() for c in chunks):
            raise DomainError(
                "no_extractable_text",
                "No usable text found. Scanned documents require OCR, which is unsupported.",
            )
        return {
            "format": suffix[1:],
            "chunks": chunks,
            "baseline": None,
            "warnings": [
                "Extracted numerical fields require explicit review before financial use."
            ],
            "rows": None,
            "columns": [],
        }
    except DomainError:
        raise
    except (ValueError, UnicodeError, zipfile.BadZipFile) as exc:
        raise DomainError("parse_failed", "Cannot parse file: " + str(exc)[:300]) from exc
    except Exception as exc:
        raise DomainError("parse_failed", "The document is invalid or unsupported.") from exc
