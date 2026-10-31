"""Statement files for the Playwright flows and manual testing (python -m app.cli walkthrough-files).

All generated and fictional: one rider ("Kumar Velu", Chennai, 60 weeks, Swiggy + Rapido) whose bank account
(fictional Vijayanagar Bank, account 9999 0000 ...) receives the platform payouts, plus files for the edge cases.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

import numpy as np

from app.sim import generate as g
from app.sim.life import live, make_persona

SEED = 4242


def _statement_image(life, acct_no: str):
    """A picture of the first statement page, for the 'photo' and 'scanned PDF' cases."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (1240, 1754), "white")
    d = ImageDraw.Draw(img)
    d.text((80, 80), "Vijayanagar Bank - Statement of Account", fill="black")
    d.text((80, 110), f"Account {acct_no}   {life.persona.name.upper()}", fill="black")
    y = 170
    for t in [t for t in life.txns if t.account == 0][:40]:
        amt = f"{t.amount:,.2f}"
        d.text((80, y), f"{t.date:%d-%m-%y}   {t.narration[:48]:<48}   {'Dr' if t.direction == 'debit' else 'Cr'} {amt:>12}", fill="black")
        y += 34
    return img


def write(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = make_persona(np.random.default_rng(SEED), SEED, "Kumar Velu", "Chennai", "rider", 60, 1)
    p.second_platform_account = 0
    life = live(p, seed=SEED)
    acct_no = g.account_no(p, 0)
    files: dict[str, bytes] = {"bank_statement.csv": g.bank_csv_vijayanagar(life, 0, acct_no)}
    for plat in p.platforms:
        files[f"{plat.lower().replace(' ', '_')}_payouts.csv"] = g.payout_csv(life, plat)

    # same account, but exported with column names the reader cannot place on its own -> "Check the columns"
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Txn Dt", "Details", "Out", "In", "Bal"])
    for t in life.txns:
        if t.account == 0:
            w.writerow([f"{t.date:%d/%m/%Y}", t.narration, f"{t.amount:.2f}" if t.direction == "debit" else "",
                        f"{t.amount:.2f}" if t.direction == "credit" else "", f"{t.balance:.2f}"])
    files["bank_statement_other_layout.csv"] = buf.getvalue().encode()

    img = _statement_image(life, acct_no)
    jpg = io.BytesIO()
    img.save(jpg, "JPEG", quality=70)
    files["statement_photo.jpg"] = jpg.getvalue()

    from fpdf import FPDF

    pdf = FPDF(format="A4")
    pdf.add_page()
    pdf.image(img, x=0, y=0, w=210)  # image only, no text layer: what a scanner produces
    files["scanned_statement.pdf"] = bytes(pdf.output())

    files["corrupted_statement.xlsx"] = g.bank_xlsx_satpura(life, 0, acct_no)[:1500]  # cut off mid-download

    written = []
    for name, data in files.items():
        path = out_dir / name
        path.write_bytes(data)
        written.append(path)
    return written
