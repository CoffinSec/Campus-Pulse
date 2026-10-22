"""Bounded UTF-8 CSV parsing with physical line provenance."""

import csv
import io
import re

import pandas as pd

from campuspulse.config import Settings
from campuspulse.models import DataError, ExtractedTable

PROVENANCE = ["source_file", "source_page", "source_table", "source_row", "row_id"]
MAX_COLUMNS = 40
MAX_CELL_LENGTH = 500
MAX_CELLS = 250000


def clean_header(value: str) -> str:
    return " ".join(str(value).split())


def validate_headers(headers: list[str]) -> list[str]:
    names = [clean_header(h) for h in headers]
    if not names or len(names) > MAX_COLUMNS or any(not h for h in names):
        raise DataError("Headers must be nonempty, with no more than 40 columns.")
    if any(re.fullmatch(r"[\d.,+ -]+", h) for h in names):
        raise DataError(
            "The first row appears to contain data rather than headers. Add descriptive column names."
        )
    folded = [re.sub(r"[\W_]+", "", h.casefold()) for h in names]
    if len(set(folded)) != len(folded):
        raise DataError("Duplicate column headers detected. Rename them before uploading.")
    if any(h in PROVENANCE or h.startswith("raw_") for h in names):
        raise DataError("Headers source_*, row_id and raw_* are reserved for provenance.")
    if any(len(h) > MAX_CELL_LENGTH for h in names):
        raise DataError("A column header exceeds the supported length.")
    return names


def parse_csv(
    data: bytes, filename: str, settings: Settings, separator: str | None = None
) -> list[ExtractedTable]:
    if not data or len(data) > settings.max_upload_mb * 1024 * 1024:
        raise DataError("CSV is empty or exceeds the configured upload limit.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DataError(
            "CSV must use UTF-8 encoding. Re-save it as CSV UTF-8 and try again."
        ) from exc
    if "\x00" in text or text.lstrip().startswith(("%PDF", "<html", "<!DOCTYPE", "PK\x03\x04")):
        raise DataError("The file contents are not a supported text CSV.")
    if separator is None:
        try:
            separator = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|").delimiter
        except csv.Error:
            separator = ","
    if separator not in {",", ";", "\t", "|"}:
        raise DataError("Select a comma, semicolon, tab or pipe separator.")
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=separator, strict=True)
    rows: list[dict] = []
    try:
        headers = validate_headers(next(reader, []))
        if len(headers) < 3:
            raise DataError(
                "CSV needs headers for building, month and electricity consumption. Check the separator."
            )
        for values in reader:
            line = reader.line_num  # End physical line, including quoted multiline records.
            if not values or all(not v.strip() for v in values):
                continue
            if len(values) != len(headers):
                raise DataError(
                    f"CSV row ending on line {line} has a different number of cells than its headers."
                )
            if any(len(v) > MAX_CELL_LENGTH for v in values):
                raise DataError(
                    f"CSV row ending on line {line} contains a cell over 500 characters."
                )
            rows.append(
                dict(zip(headers, values))
                | {
                    "source_file": filename,
                    "source_page": None,
                    "source_table": 1,
                    "source_row": line,
                    "row_id": f"csv:1:{line}",
                }
            )
            if len(rows) > settings.max_rows or len(rows) * len(headers) > MAX_CELLS:
                raise DataError(
                    "CSV exceeds the supported row or cell limit. Upload a smaller dataset."
                )
    except csv.Error as exc:
        raise DataError(
            "Malformed CSV quoting or oversized field. Re-export the file as UTF-8 CSV."
        ) from exc
    if not rows:
        raise DataError("CSV contains no data rows.")
    return [ExtractedTable("CSV table 1", pd.DataFrame(rows))]
