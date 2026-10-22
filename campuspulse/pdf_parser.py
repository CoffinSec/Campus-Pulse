"""Extract real tables using PyMuPDF. Tables are never silently merged."""

import pandas as pd
import pymupdf

from campuspulse.config import Settings
from campuspulse.csv_parser import MAX_CELL_LENGTH, MAX_CELLS, clean_header, validate_headers
from campuspulse.models import Caveat, DataError, ExtractedTable


def parse_pdf(data: bytes, filename: str, settings: Settings) -> list[ExtractedTable]:
    if not data.startswith(b"%PDF-"):
        raise DataError("This file does not contain a valid PDF signature.")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise DataError("PDF exceeds the configured upload limit.")
    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except (pymupdf.FileDataError, RuntimeError) as exc:
        raise DataError("This PDF is damaged or unreadable. Re-export it or upload a CSV.") from exc
    with document:
        if document.needs_pass:
            raise DataError("Password-protected PDFs are not supported. Upload an unlocked export.")
        if not 1 <= document.page_count <= settings.max_pdf_pages:
            raise DataError(f"PDF must contain 1–{settings.max_pdf_pages} pages.")
        tables: list[ExtractedTable] = []
        has_text = False
        total_rows = total_cells = detected = 0
        for page_num, page in enumerate(document, start=1):
            has_text = has_text or bool(page.get_text().strip())
            found = page.find_tables()
            page_tables = found.tables
            if not page_tables and page.get_text().strip():
                # A bounded fallback for aligned text tables without grid lines.
                page_tables = page.find_tables(strategy="text").tables
            for table_num, table in enumerate(page_tables, start=1):
                detected += 1
                if detected > settings.max_tables:
                    raise DataError("PDF exceeds the configured table limit. Upload fewer pages.")
                extracted = table.extract()
                if not extracted:
                    continue
                external = table.header.external
                raw_headers = table.header.names if external else extracted[0]
                raw_headers = ["" if v is None else v for v in raw_headers]
                warnings = []
                try:
                    headers = validate_headers(raw_headers)
                except DataError:
                    headers = [f"Column {i + 1}" for i in range(len(raw_headers))]
                    validate_headers(headers)
                    warnings.append(
                        Caveat(
                            severity="warning",
                            code="pdf_headers",
                            message="Missing or duplicate PDF headers. Review the original document and map columns explicitly.",
                        )
                    )
                records = extracted if external else extracted[1:]
                rows = []
                for row_num, cells in enumerate(records, start=1 if external else 2):
                    values = [clean_header(v) if v is not None else "" for v in cells]
                    if not any(values) or values == [clean_header(h) for h in raw_headers]:
                        continue
                    if len(values) != len(headers):
                        raise DataError(
                            f"Broken table on page {page_num}: inconsistent row widths. Try a CSV export."
                        )
                    if any(len(v) > MAX_CELL_LENGTH for v in values):
                        raise DataError(
                            "A PDF cell exceeds the supported length. Use a smaller structured report."
                        )
                    rows.append(
                        dict(zip(headers, values))
                        | {
                            "source_file": filename,
                            "source_page": page_num,
                            "source_table": table_num,
                            "source_row": row_num,
                            "row_id": f"pdf:{page_num}:{table_num}:{row_num}",
                        }
                    )
                    total_rows += 1
                    total_cells += len(headers)
                    if total_rows > settings.max_rows or total_cells > MAX_CELLS:
                        raise DataError("PDF exceeds the supported row or cell limit.")
                if rows:
                    warnings.append(
                        Caveat(
                            severity="info",
                            code="pdf_review",
                            message="PDF table extraction can misread layout. Confirm column mapping, values and units against the original page.",
                        )
                    )
                    tables.append(
                        ExtractedTable(
                            f"Page {page_num} · Table {table_num}", pd.DataFrame(rows), warnings
                        )
                    )
        if not tables:
            if not has_text:
                raise DataError(
                    "This appears to be a scanned or image-only PDF. OCR is not included; upload a searchable table PDF or CSV."
                )
            raise DataError(
                "This PDF does not contain a recognizable structured table. Try another file or upload a CSV."
            )
        return tables
