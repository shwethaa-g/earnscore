"""Statement parsers: CSV / XLSX / text PDF bank statements and platform payout statements.

Contract (DATA_SOURCES.md section 4): any column order, auto-detected mapping with a confidence score
(the UI asks the user to map columns when confidence < 0.9), dd/mm/yyyy, dd-mm-yy and yyyy-mm-dd dates,
debit/credit columns or one signed amount column, and no silent row drops (every skipped row has a reason).
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

MAPPING_CONFIDENCE_REQUIRED = 0.9

SYNONYMS: dict[str, list[str]] = {
    "date": ["date", "txn date", "transaction date", "tran date", "value date", "posting date", "value dt", "txn dt",
             "payout date", "settlement date"],
    "narration": ["narration", "description", "particulars", "remarks", "details", "transaction details",
                  "transaction remarks", "transaction description"],
    "debit": ["debit", "withdrawal", "withdrawals", "debit amount", "withdrawal amt", "withdrawal amount", "dr",
              "debit amt", "withdrawal amt."],
    "credit": ["credit", "deposit", "deposits", "credit amount", "deposit amt", "deposit amount", "cr", "credit amt",
               "deposit amt."],
    "amount": ["amount", "txn amount", "transaction amount", "amount (inr)", "amount(inr)", "payout amount",
               "net payout", "payout", "amount (rs)"],
    "drcr": ["dr/cr", "cr/dr", "type", "txn type", "debit/credit"],
    "balance": ["balance", "closing balance", "running balance", "available balance", "balance (inr)", "bal"],
    "ref": ["ref", "reference", "ref no", "ref no.", "chq/ref no", "chq / ref no.", "chq./ref.no.", "utr",
            "cheque no", "reference no", "payout reference", "payout ref", "transaction id", "payout id"],
    "trips": ["trips", "tasks", "orders", "jobs", "deliveries", "rides", "trips/tasks"],
    "active_hours": ["active hours", "hours", "online hours", "login hours", "active hrs"],
    "platform": ["platform", "partner", "company", "aggregator"],
}

DATE_FORMATS = {
    "dd/mm/yyyy": ["%d/%m/%Y", "%d/%m/%y"],
    "dd-mm-yy": ["%d-%m-%y", "%d-%m-%Y", "%d-%b-%y", "%d-%b-%Y", "%d %b %Y", "%d %b %y"],
    "yyyy-mm-dd": ["%Y-%m-%d", "%Y/%m/%d"],
    "mm/dd/yyyy": ["%m/%d/%Y"],
}
AUTO_ORDER = ["dd/mm/yyyy", "dd-mm-yy", "yyyy-mm-dd"]


class ParseError(Exception):
    """A file could not be read at all; the message is shown to the user."""


@dataclass
class Table:
    columns: list[str]
    rows: list[list[str]]
    header_row: int = 0  # 1-based line number of the header in the original file


@dataclass
class ParsedRow:
    row_number: int
    date: date
    narration: str
    direction: str
    amount: float
    balance: float | None = None
    ref: str = ""
    platform: str = ""
    trips: int | None = None
    active_hours: float | None = None


@dataclass
class ParseResult:
    rows: list[ParsedRow] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)


def _norm(s: object) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


# ---------- reading files into a raw table ----------

def _find_header(rows: list[list[str]]) -> int:
    """Index of the first row that looks like a header (bank CSVs often start with account details)."""
    best, best_hits = 0, -1
    for i, row in enumerate(rows[:40]):
        cells = [_norm(c) for c in row]
        hits = sum(1 for c in cells if any(c == syn for syns in SYNONYMS.values() for syn in syns))
        if hits > best_hits:
            best, best_hits = i, hits
        if hits >= 3:
            return i
    return best


def _to_table(rows: list[list[str]]) -> Table:
    rows = [[str(c).strip() if c is not None else "" for c in r] for r in rows]
    rows = [r for r in rows if any(c for c in r)] if rows else rows
    if not rows:
        raise ParseError("The file is empty.")
    h = _find_header(rows)
    header = rows[h]
    width = len(header)
    cols, seen = [], {}
    for i, c in enumerate(header):
        name = c or f"Column {i + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name} ({seen[name]})"
        else:
            seen[name] = 1
        cols.append(name)
    body = [(r + [""] * width)[:width] for r in rows[h + 1:]]
    return Table(columns=cols, rows=body, header_row=h + 1)


def read_csv(data: bytes) -> Table:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ParseError("We could not read the text in this file. Save it as UTF-8 CSV and try again.")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
        delim = dialect.delimiter
    except csv.Error:
        delim = ","
    return _to_table(list(csv.reader(io.StringIO(text), delimiter=delim)))


def read_xlsx(data: bytes) -> Table:
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as e:  # openpyxl raises many types for corrupt files
        raise ParseError("This Excel file could not be opened. Check that it is a valid .xlsx file.") from e
    ws = wb.worksheets[0]
    rows = []
    for r in ws.iter_rows(values_only=True):
        rows.append(["" if v is None else (v.strftime("%Y-%m-%d") if isinstance(v, (datetime, date)) else str(v)) for v in r])
    return _to_table(rows)


def read_pdf(data: bytes) -> Table:
    import pdfplumber

    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception as e:
        raise ParseError("This PDF could not be opened. Upload the statement as CSV or Excel instead.") from e
    all_rows: list[list[str]] = []
    any_text = False
    with pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            any_text = any_text or bool(text.strip())
            for tbl in page.extract_tables():
                for r in tbl:
                    all_rows.append([(c or "").replace("\n", " ") for c in r])
    if not any_text:
        raise ParseError("This PDF has no readable text (it looks like a scanned image). "
                         "Scanned statements are not supported; please download a CSV or Excel statement from your bank.")
    if not all_rows:
        raise ParseError("We could not find a transaction table in this PDF. Please upload the CSV or Excel version of the statement.")
    table = _to_table(all_rows)
    # Multi-page PDFs repeat the header on each page; drop repeats.
    header_norm = [_norm(c) for c in table.columns]
    table.rows = [r for r in table.rows if [_norm(c) for c in r] != header_norm]
    return table


def read_table(data: bytes, file_type: str) -> Table:
    if file_type == "csv":
        return read_csv(data)
    if file_type == "xlsx":
        return read_xlsx(data)
    if file_type == "pdf":
        return read_pdf(data)
    raise ParseError("Unsupported file type. Upload CSV, XLSX or PDF.")


def sniff_type(filename: str, data: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if data[:4] == b"%PDF":
        return "pdf"
    if data[:2] == b"PK":
        return "xlsx"
    if ext in {".csv", ".txt"}:
        if b"\x00" in data[:2048]:
            raise ParseError("This file does not look like a text CSV.")
        return "csv"
    raise ParseError("Unsupported file type. Upload CSV, XLSX or PDF.")


# ---------- value parsing ----------

def parse_amount(s: object) -> float | None:
    t = str(s or "").strip()
    if not t or t in {"-", "--"}:
        return None
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()")
    suffix = re.search(r"\b(cr|dr)\.?$", t, re.I)
    t = re.sub(r"(?i)(inr|rs\.?|₹|\bcr\.?$|\bdr\.?$)", "", t).replace(",", "").replace(" ", "")
    if t.startswith("+"):
        t = t[1:]
    try:
        v = float(t)
    except ValueError:
        return None
    if neg:
        v = -abs(v)
    if suffix and suffix.group(1).lower() == "dr":
        v = -abs(v)
    return v


def parse_date(s: object, fmt_key: str) -> date | None:
    t = str(s or "").strip()
    if not t:
        return None
    t = t.split(" ")[0] if re.match(r"^\d{4}-\d{2}-\d{2} \d", t) else t
    for f in DATE_FORMATS.get(fmt_key, []):
        try:
            return datetime.strptime(t, f).date()
        except ValueError:
            continue
    return None


def detect_date_format(values: list[str]) -> tuple[str, float]:
    vals = [v for v in values if str(v).strip()][:200]
    if not vals:
        return "dd/mm/yyyy", 0.0
    best, best_rate = AUTO_ORDER[0], -1.0
    for key in AUTO_ORDER:
        rate = sum(1 for v in vals if parse_date(v, key)) / len(vals)
        if rate > best_rate:
            best, best_rate = key, rate
    return best, best_rate


# ---------- column mapping ----------

def detect_mapping(table: Table, kind: str = "bank_statement") -> tuple[dict, float]:
    """Return (mapping, confidence). Mapping values are column names from the table."""
    norm_cols = {c: _norm(c) for c in table.columns}
    mapping: dict[str, str | None] = {}
    used: set[str] = set()
    for field_name, syns in SYNONYMS.items():
        hit = None
        for c, n in norm_cols.items():
            if c not in used and n in syns:
                hit = c
                break
        if hit is None:
            for c, n in norm_cols.items():
                if c not in used and any(n.startswith(s) for s in syns if len(s) > 3):
                    hit = c
                    break
        mapping[field_name] = hit
        if hit:
            used.add(hit)

    sample = table.rows[:200]
    idx = {c: i for i, c in enumerate(table.columns)}

    def col_vals(name):
        return [r[idx[name]] for r in sample] if name else []

    checks = []
    fmt, date_rate = detect_date_format(col_vals(mapping["date"])) if mapping["date"] else ("dd/mm/yyyy", 0.0)
    mapping["date_format"] = fmt
    checks.append(date_rate)
    has_amount = bool(mapping["debit"] or mapping["credit"] or mapping["amount"])
    if mapping["debit"] or mapping["credit"]:
        vals = col_vals(mapping["debit"]) + col_vals(mapping["credit"])
        nonempty = [v for v in vals if str(v).strip() not in {"", "-"}]
        checks.append(sum(1 for v in nonempty if parse_amount(v) is not None) / max(len(nonempty), 1))
        mapping["amount"] = None
    elif mapping["amount"]:
        vals = [v for v in col_vals(mapping["amount"]) if str(v).strip()]
        checks.append(sum(1 for v in vals if parse_amount(v) is not None) / max(len(vals), 1))
    else:
        checks.append(0.0)
    if kind == "bank_statement":
        checks.append(1.0 if mapping["narration"] else 0.0)
    if not has_amount or not mapping["date"]:
        return mapping, 0.0
    return mapping, round(min(checks), 3)


def normalize(table: Table, mapping: dict, kind: str = "bank_statement", default_platform: str = "") -> ParseResult:
    """Turn raw rows into ParsedRow objects. Every row is either parsed or listed in `skipped` with a reason."""
    idx = {c: i for i, c in enumerate(table.columns)}
    fmt = mapping.get("date_format") or "auto"
    if fmt == "auto":
        fmt, _ = detect_date_format([r[idx[mapping["date"]]] for r in table.rows]) if mapping.get("date") else ("dd/mm/yyyy", 0)

    def get(row, key):
        col = mapping.get(key)
        return row[idx[col]] if col and col in idx else ""

    res = ParseResult()
    for i, row in enumerate(table.rows):
        line = table.header_row + 1 + i
        if not any(str(c).strip() for c in row):
            continue
        raw_date = get(row, "date")
        d = parse_date(raw_date, fmt)
        narration = str(get(row, "narration")).strip()
        if d is None:
            low = " ".join(str(c) for c in row).lower()
            reason = "summary or total line" if any(k in low for k in ("total", "opening balance", "closing balance", "balance b/f", "carried forward")) else f"unreadable date '{raw_date}'"
            res.skipped.append({"row": line, "reason": reason})
            continue
        if mapping.get("debit") or mapping.get("credit"):
            dr = parse_amount(get(row, "debit"))
            cr = parse_amount(get(row, "credit"))
            if (dr is None or dr == 0) and (cr is None or cr == 0):
                res.skipped.append({"row": line, "reason": "no debit or credit amount"})
                continue
            if cr and cr != 0 and (dr is None or dr == 0):
                direction, amount = "credit", abs(cr)
            elif dr and dr != 0 and (cr is None or cr == 0):
                direction, amount = "debit", abs(dr)
            else:
                res.skipped.append({"row": line, "reason": "both debit and credit filled"})
                continue
        else:
            amt = parse_amount(get(row, "amount"))
            if amt is None or amt == 0:
                res.skipped.append({"row": line, "reason": f"unreadable amount '{get(row, 'amount')}'"})
                continue
            drcr = _norm(get(row, "drcr"))
            if kind == "platform_statement":
                direction = "credit" if amt > 0 else "debit"
            elif drcr in {"dr", "debit", "d", "withdrawal"}:
                direction = "debit"
            elif drcr in {"cr", "credit", "c", "deposit"}:
                direction = "credit"
            else:
                direction = "credit" if amt > 0 else "debit"
            amount = abs(amt)
        trips_raw = parse_amount(get(row, "trips"))
        hours_raw = parse_amount(get(row, "active_hours"))
        res.rows.append(ParsedRow(
            row_number=line, date=d, narration=narration[:500], direction=direction, amount=round(amount, 2),
            balance=parse_amount(get(row, "balance")), ref=str(get(row, "ref")).strip()[:80],
            platform=(str(get(row, "platform")).strip() or default_platform)[:60],
            trips=int(trips_raw) if trips_raw is not None else None,
            active_hours=float(hours_raw) if hours_raw is not None else None,
        ))
    return res


def preview(table: Table, n: int = 8) -> dict:
    return {"columns": table.columns, "rows": table.rows[:n], "total_rows": len(table.rows)}
