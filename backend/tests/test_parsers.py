import io
from datetime import date

import pytest

from app.ingest import parsers


def table(text: str) -> parsers.Table:
    return parsers.read_csv(text.encode())


def test_two_column_csv_with_preamble_and_ddmmyyyy():
    t = table("Bank X Statement\nAccount,123\n\nTxn Date,Description,Debit,Credit,Balance\n"
              '01/02/2026,UPI/CR/1/ARUN,,"1,200.50",5000\n03/02/2026,RENT,4000,,1000\n')
    m, conf = parsers.detect_mapping(t)
    assert conf >= parsers.MAPPING_CONFIDENCE_REQUIRED
    res = parsers.normalize(t, m)
    assert [(r.date, r.direction, r.amount) for r in res.rows] == [(date(2026, 2, 1), "credit", 1200.5), (date(2026, 2, 3), "debit", 4000.0)]
    assert res.rows[0].balance == 5000


def test_signed_amount_with_drcr_column_and_iso_dates():
    t = table("Transaction Date,Particulars,Amount (INR),Dr/Cr,Balance (INR)\n2026-03-01,SWIGGY,950.00,CR,100\n2026-03-02,FUEL,300.00,DR,50\n")
    m, conf = parsers.detect_mapping(t)
    assert conf >= 0.9 and m["amount"] and m["drcr"]
    rows = parsers.normalize(t, m).rows
    assert [r.direction for r in rows] == ["credit", "debit"]


def test_single_signed_column_and_ddmmyy():
    t = table("Date,Narration,Amount\n05-01-26,UPI/CR/9/X,500\n06-01-26,ATM,-200\n")
    m, _ = parsers.detect_mapping(t)
    assert m["date_format"] == "dd-mm-yy"
    rows = parsers.normalize(t, m).rows
    assert rows[0].date == date(2026, 1, 5) and rows[1].direction == "debit" and rows[1].amount == 200


def test_malformed_rows_are_reported_never_dropped():
    t = table("Date,Narration,Debit,Credit\n01/01/2026,A,,100\nnot a date,B,,100\n02/01/2026,C,,\n,Opening Balance,,\n03/01/2026,D,50,\n")
    m, _ = parsers.detect_mapping(t)
    res = parsers.normalize(t, m)
    assert len(res.rows) == 2
    reasons = [s["reason"] for s in res.skipped]
    assert any("unreadable date" in r for r in reasons) and any("no debit or credit" in r for r in reasons)
    assert len(res.rows) + len(res.skipped) == 5  # every non-blank input row is either parsed or reported


def test_low_confidence_mapping_when_headers_unknown():
    t = table("Col1,Col2,Col3\n01/01/2026,hello,100\n")
    _, conf = parsers.detect_mapping(t)
    assert conf < parsers.MAPPING_CONFIDENCE_REQUIRED


def test_amount_parsing_variants():
    assert parsers.parse_amount("1,23,456.75") == 123456.75
    assert parsers.parse_amount("₹ 500") == 500
    assert parsers.parse_amount("(250.00)") == -250
    assert parsers.parse_amount("120.00 Dr") == -120
    assert parsers.parse_amount("") is None and parsers.parse_amount("abc") is None


def test_xlsx_parser():
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Tran Date", "Remarks", "Debit", "Credit", "Balance"])
    ws.append(["01/04/2026", "UPI/CR/1/A", None, 700, 700])
    buf = io.BytesIO()
    wb.save(buf)
    t = parsers.read_table(buf.getvalue(), parsers.sniff_type("s.xlsx", buf.getvalue()))
    m, conf = parsers.detect_mapping(t)
    assert conf >= 0.9 and parsers.normalize(t, m).rows[0].amount == 700


def test_text_pdf_parser_and_scanned_pdf_message():
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=9)
    with pdf.table() as tbl:
        tbl.row(["Date", "Description", "Debit", "Credit", "Balance"])
        tbl.row(["01/05/2026", "UPI/CR/77/MEENA", "", "1,000.00", "1,000.00"])
        tbl.row(["02/05/2026", "BBPS/TANGEDCO", "400.00", "", "600.00"])
    data = bytes(pdf.output())
    t = parsers.read_table(data, "pdf")
    m, conf = parsers.detect_mapping(t)
    rows = parsers.normalize(t, m).rows
    assert conf >= 0.9 and len(rows) == 2 and rows[1].direction == "debit"

    blank = FPDF()
    blank.add_page()
    with pytest.raises(parsers.ParseError, match="scanned"):
        parsers.read_table(bytes(blank.output()), "pdf")


def test_unsupported_type():
    with pytest.raises(parsers.ParseError, match="Photos"):
        parsers.sniff_type("photo.jpg", b"\xff\xd8\xff")
    with pytest.raises(parsers.ParseError, match=r"\.xls"):
        parsers.sniff_type("statement.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    with pytest.raises(parsers.ParseError, match="Unsupported file type"):
        parsers.sniff_type("statement.docx", b"PK\x03\x04")
    assert parsers.sniff_type("statement.xlsx", b"PK\x03\x04") == "xlsx"


def test_platform_payout_statement():
    t = table("Payout Date,Platform,Payout Reference,Trips,Active Hours,Payout Amount\n2026-06-03,Swiggy,SWI1,42,31.5,2100.00\n")
    m, conf = parsers.detect_mapping(t, "platform_statement")
    r = parsers.normalize(t, m, "platform_statement").rows[0]
    assert conf >= 0.9 and r.platform == "Swiggy" and r.trips == 42 and r.active_hours == 31.5 and r.ref == "SWI1"
