import pandas as pd
import pymupdf
import pytest

from campuspulse.config import Settings
from campuspulse.csv_parser import parse_csv
from campuspulse.ingestion import ingest, safe_filename
from campuspulse.models import DataError
from campuspulse.normalization import normalize, suggest_mapping
from campuspulse.pdf_parser import parse_pdf


@pytest.mark.parametrize(
    "prefix,separator", [(b"", b","), (b"\xef\xbb\xbf", b","), (b"", b";"), (b"", b"\t")]
)
def test_csv_encoding_delimiter_and_rows(csv_bytes, settings, prefix, separator):
    frame = parse_csv(prefix + csv_bytes.replace(b",", separator), "sample.csv", settings)[0].frame
    assert len(frame) == 30
    assert frame.source_row.tolist() == list(range(2, 32))
    assert frame.source_page.isna().all()


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"a,b,c\n",
        b"a,,c\n1,2,3",
        b"Building,Building,kWh\nA,A,1",
        b"Block,2026-06,2\nA,2026-05,4",
        b"a,b,c\n1,2",
        b"a,b,c\n\xff,1,2",
        b"a,b,c\n1,\x00,3",
        b"%PDF-1.7\na,b,c",
        b'a,b,c\n"unclosed,2,3',
    ],
)
def test_csv_rejects_invalid_content(data, settings):
    with pytest.raises(DataError):
        parse_csv(data, "bad.csv", settings)


def test_csv_multiline_physical_end_line(settings):
    data = b'Building,Month,kWh\n"Academic\nBlock A",2026-06,50\n'
    frame = parse_csv(data, "a.csv", settings)[0].frame
    assert frame.iloc[0].source_row == 3


def test_row_and_size_limits(csv_bytes):
    with pytest.raises(DataError, match="limit"):
        parse_csv(csv_bytes, "a.csv", Settings(max_rows=2))
    with pytest.raises(DataError, match="1 MB"):
        ingest(b"x" * (1024 * 1024 + 1), "a.csv", Settings(max_upload_mb=1))


def test_pdf_matches_csv(pdf_bytes, csv_bytes, settings):
    pdf = parse_pdf(pdf_bytes, "report.pdf", settings)
    csv = parse_csv(csv_bytes, "report.csv", settings)
    assert len(pdf) == 1
    left, right = [
        normalize(tables[0], suggest_mapping(list(tables[0].frame)), "kWh").frame
        for tables in [pdf, csv]
    ]
    cols = ["building_name", "month", "electricity_kwh"]
    pd.testing.assert_frame_equal(left[cols], right[cols])
    assert left.source_page.eq(1).all()
    assert left.source_row.tolist() == list(range(2, 32))


def test_pdf_multiple_pages_separate_tables(pdf_bytes, settings):
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as source, pymupdf.open() as doc:
        doc.insert_pdf(source)
        doc.insert_pdf(source)
        content = doc.tobytes()
    tables = parse_pdf(content, "multi.pdf", settings)
    assert len(tables) == 2
    assert tables[1].frame.source_page.eq(2).all()
    assert set(tables[0].frame.row_id).isdisjoint(set(tables[1].frame.row_id))
    with pytest.raises(DataError, match="pages"):
        parse_pdf(content, "multi.pdf", Settings(max_pdf_pages=1))
    with pytest.raises(DataError, match="table limit"):
        parse_pdf(content, "multi.pdf", Settings(max_tables=1))


@pytest.mark.parametrize("text", [None, "This report has no table."])
def test_pdf_without_table(settings, text):
    with pymupdf.open() as doc:
        page = doc.new_page()
        if text:
            page.insert_text((50, 50), text)
        content = doc.tobytes()
    with pytest.raises(DataError, match="scanned|recognizable"):
        parse_pdf(content, "report.pdf", settings)


@pytest.mark.parametrize("content", [b"not pdf", b"%PDF-1.7\ninvalid"])
def test_invalid_pdf(content, settings):
    with pytest.raises(DataError):
        parse_pdf(content, "invalid.pdf", settings)


def test_password_pdf(pdf_bytes, settings):
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        content = doc.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="test-owner", user_pw="test-user"
        )
    with pytest.raises(DataError, match="Password"):
        parse_pdf(content, "locked.pdf", settings)


def draw_test_table(page, top, headers, records):
    """Real PDF grid fixture, including deliberately malformed cell/header cases."""
    xs = [40, 220, 360, 520]
    rows = [headers, *records]
    for index, row in enumerate(rows):
        for column, value in enumerate(row):
            page.insert_text((xs[column] + 5, top + index * 24 + 15), value, fontsize=10)
    for x in xs:
        page.draw_line((x, top), (x, top + len(rows) * 24))
    for index in range(len(rows) + 1):
        page.draw_line((xs[0], top + index * 24), (xs[-1], top + index * 24))


def test_two_tables_on_same_page_and_repeated_header(settings):
    with pymupdf.open() as doc:
        page = doc.new_page()
        header = ["Building", "Month", "kWh"]
        draw_test_table(page, 50, header, [["A", "2026-05", "10"], header, ["A", "2026-06", "12"]])
        draw_test_table(page, 300, header, [["B", "2026-06", "20"]])
        content = doc.tobytes()
    tables = parse_pdf(content, "two-tables.pdf", settings)
    assert len(tables) == 2
    assert len(tables[0].frame) == 2
    assert tables[0].frame.source_row.tolist() == [2, 4]
    assert tables[1].frame.source_table.eq(2).all()


def test_pdf_duplicate_headers_and_broken_value_require_review(settings):
    with pymupdf.open() as doc:
        page = doc.new_page()
        draw_test_table(page, 50, ["Building", "Building", "kWh"], [["A", "2026-06", "broken"]])
        content = doc.tobytes()
    table = parse_pdf(content, "broken.pdf", settings)[0]
    assert any(w.code == "pdf_headers" for w in table.warnings)
    with pytest.raises(DataError, match="numeric"):
        normalize(
            table,
            {"building_name": "Column 1", "month": "Column 2", "electricity_kwh": "Column 3"},
            "kWh",
        )


@pytest.mark.parametrize("extension", ["csv", "pdf"])
def test_isolated_ingestion(csv_bytes, pdf_bytes, settings, extension):
    tables = ingest(
        csv_bytes if extension == "csv" else pdf_bytes, f"../nested/report.{extension}", settings
    )
    assert len(tables[0].frame) == 30
    assert tables[0].frame.source_file.eq(f"report.{extension}").all()


def test_extension_and_safe_name(settings):
    assert safe_filename(r"C:\secrets\my report.pdf") == "my report.pdf"
    with pytest.raises(DataError, match="Only PDF"):
        ingest(b"data", "x.exe", settings)
    with pytest.raises(DataError, match="signature"):
        ingest(b"a,b,c\n1,2,3", "fake.pdf", settings)
