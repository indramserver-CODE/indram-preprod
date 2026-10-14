"""
app/services/pdf_service.py
----------------------------
  generate_resident_bill_pdf — a flat's bill on the society letterhead (optionally with late fee)
  generate_society_bill_pdf  — the society admin's three bills: society total / MSEB only / Indram + GST
  generate_indram_invoice_pdf — Indram's GST tax invoice to the society
  generate_resident_receipt_pdf — a flat's payment receipt on the society letterhead
  generate_indram_receipt_pdf — receipt for a paid Indram invoice

Amounts are printed as "Rs." — the built-in PDF fonts have no ₹ glyph.
"""

import io
from datetime import date
from decimal import Decimal
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image, KeepTogether,
)

from app.services.billing_calc import amount_in_words, GST_HALF_RATE, IST, round2

_PRIMARY  = colors.HexColor("#1a3c5e")
_ACCENT   = colors.HexColor("#4f86f7")
_LIGHT_BG = colors.HexColor("#f0f4f8")
_GRID     = colors.HexColor("#e2e8f0")
_TOTAL    = colors.HexColor("#c53030")
_GREEN    = colors.HexColor("#276749")
_WIDTH    = 170 * mm

_styles = getSampleStyleSheet()
_S = {
    "title":   ParagraphStyle("title", parent=_styles["Normal"], fontSize=16, textColor=_PRIMARY,
                              fontName="Helvetica-Bold", alignment=TA_CENTER, leading=20, spaceAfter=2),
    "sub":     ParagraphStyle("sub", parent=_styles["Normal"], fontSize=9, textColor=colors.grey, alignment=TA_CENTER),
    "label":   ParagraphStyle("label", parent=_styles["Normal"], fontSize=8, textColor=colors.grey),
    "value":   ParagraphStyle("value", parent=_styles["Normal"], fontSize=9, textColor=_PRIMARY, fontName="Helvetica-Bold"),
    "section": ParagraphStyle("section", parent=_styles["Normal"], fontSize=10, textColor=colors.white, fontName="Helvetica-Bold"),
    "body":    ParagraphStyle("body", parent=_styles["Normal"], fontSize=9, leading=12),
    "small":   ParagraphStyle("small", parent=_styles["Normal"], fontSize=8, textColor=colors.grey, alignment=TA_CENTER),
    "right":   ParagraphStyle("right", parent=_styles["Normal"], fontSize=9, alignment=TA_RIGHT),
}


# ── Shared building blocks ────────────────────────────────────────────

def rs(amount) -> str:
    """Rs. 12,34,567.50 — Indian digit grouping."""
    return f"Rs. {_indian(amount)}" if Decimal(str(amount)) >= 0 else f"-Rs. {_indian(-Decimal(str(amount)))}"


def _indian(amount) -> str:
    """12,34,567.50 — Indian digit grouping, no currency."""
    amount = Decimal(str(amount)).quantize(Decimal("0.01"))
    sign, amount = ("-", -amount) if amount < 0 else ("", amount)
    whole, frac = f"{amount:.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return f"{sign}{whole}.{frac}"


def _kwh(units) -> str:
    return f"{Decimal(str(units)):.3f}"


def _d(value: date | None) -> str:
    return value.strftime("%d %b %Y") if value else "—"


def _period(period_from: date, period_till: date) -> str:
    return f"{_d(period_from)} – {_d(period_till)}"


def _doc(buffer: io.BytesIO) -> SimpleDocTemplate:
    return SimpleDocTemplate(buffer, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm,
                             topMargin=15*mm, bottomMargin=18*mm)


def _letterhead(letterhead: bytes | None, society_name: str, society_address: str | None) -> list:
    """The society's uploaded header image, or a plain name/address header when none is set."""
    if letterhead:
        try:
            reader = ImageReader(io.BytesIO(letterhead))
            w, h   = reader.getSize()
            height = min(_WIDTH * h / w, 40 * mm)
            return [Image(io.BytesIO(letterhead), width=height * w / h, height=height), Spacer(1, 3*mm),
                    HRFlowable(width="100%", thickness=1.5, color=_ACCENT), Spacer(1, 4*mm)]
        except Exception:
            pass   # unreadable image — fall back to text header
    out = [Paragraph(society_name, _S["title"])]
    if society_address:
        out.append(Paragraph(society_address, _S["sub"]))
    return out + [Spacer(1, 3*mm), HRFlowable(width="100%", thickness=1.5, color=_ACCENT), Spacer(1, 4*mm)]


def _section(title: str) -> Table:
    t = Table([[Paragraph(title, _S["section"])]], colWidths=[_WIDTH])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), _PRIMARY),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8)]))
    return t


def _info_grid(pairs: list[tuple[str, str]], cols: int = 3) -> Table:
    """Label/value cells laid out `cols` per row."""
    rows, row = [], []
    for label, value in pairs:
        row.append([Paragraph(label, _S["label"]), Paragraph(value or "—", _S["value"])])
        if len(row) == cols:
            rows.append(row)
            row = []
    if row:
        rows.append(row + [""] * (cols - len(row)))
    t = Table(rows, colWidths=[_WIDTH / cols] * cols)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, _GRID), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    return t


def _table(data: list[list], widths: list[float], right_cols: tuple[int, ...] = (), bold_last: bool = False) -> Table:
    t = Table(data, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), _LIGHT_BG), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("GRID", (0, 0), (-1, -1), 0.5, _GRID),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    for c in right_cols:
        style.append(("ALIGN", (c, 0), (c, -1), "RIGHT"))
    if bold_last:
        style += [("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("BACKGROUND", (0, -1), (-1, -1), _LIGHT_BG)]
    t.setStyle(TableStyle(style))
    return t


def _total_bar(label: str, amount, color=_TOTAL) -> Table:
    t = Table([[label, rs(amount)]], colWidths=[_WIDTH - 45*mm, 45*mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), color), ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
                           ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 11),
                           ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8), ("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    return t


def _payment_lines(society: dict) -> list[str]:
    lines = []
    if society.get("payee_name"):
        lines.append(f"<b>Pay to:</b> {society['payee_name']}")
    bank = ", ".join(x for x in (
        society.get("bank_name"),
        f"A/c {society['bank_account_no']}" if society.get("bank_account_no") else None,
        f"IFSC {society['bank_ifsc']}" if society.get("bank_ifsc") else None,
    ) if x)
    if bank:
        lines.append(f"<b>Bank transfer:</b> {bank}")
    if society.get("upi_id"):
        lines.append(f"<b>UPI:</b> {society['upi_id']}")
    if society.get("payment_note"):
        lines.append(society["payment_note"])
    return lines or ["Pay your society as per the society's payment instructions."]


def _mseb_reference(bill: dict) -> Table:
    return _info_grid([
        ("MSEB bill period",    _period(bill["period_from"], bill["period_till"])),
        ("MSEB bill amount",    rs(bill["mseb_amount"])),
        ("MSEB bill units",     f"{_kwh(bill['mseb_units'])} kWh"),
        ("Effective rate",      f"{rs(bill['effective_rate'])} / kWh"),
    ], cols=4)


def _build(buffer: io.BytesIO, elements: list, footer: str):
    """Build the PDF with `footer` drawn at the bottom of every page (never pushed to a page of its own)."""
    line = f"{footer} Generated on {date.today():%d %b %Y}."

    def draw(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(_GRID)
        canvas.line(doc.leftMargin, 12*mm, doc.leftMargin + _WIDTH, 12*mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.grey)
        canvas.drawCentredString(A4[0] / 2, 8*mm, line)
        canvas.restoreState()

    _doc(buffer).build(elements, onFirstPage=draw, onLaterPages=draw)


# ── 1. Resident bill ──────────────────────────────────────────────────

def generate_resident_bill_pdf(society: dict, bill: dict, flat: dict, sessions: list[dict],
                               letterhead: bytes | None = None, late_fee: Decimal | None = None,
                               late_fee_pct: Decimal | None = None) -> bytes:
    """
    society  — name, address, payee_name, bank_name, bank_account_no, bank_ifsc, upi_id, payment_note
    bill     — period_from, period_till, due_date, tariff, effective_rate, mseb_amount, mseb_units, meter_label
    flat     — FlatBill fields as a dict (bill_number, flat_number, owner_name, charger_id, rfid_uids, units…)
    sessions — [{started_at, ended_at (IST datetimes), units, is_adjustment}]
    late_fee — set for the "Unpaid" re-send: bill plus late fee
    """
    buffer = io.BytesIO()
    el = _letterhead(letterhead, society["name"], society.get("address"))
    title = "EV Charging Bill — Unpaid, Late Fee Added" if late_fee else "EV Charging Bill"
    el += [Paragraph(title, _S["title"]), Spacer(1, 3*mm)]

    el.append(_info_grid([
        ("Bill No.",     flat["bill_number"] or "DRAFT"),
        ("Bill period",  _period(bill["period_from"], bill["period_till"])),
        ("Due date",     _d(bill["due_date"])),
        ("Society",      society["name"]),
        ("Flat",         flat["flat_number"]),
        ("Owner",        flat.get("owner_name") or "—"),
        ("Charger ID",   flat.get("charger_id") or "—"),
        ("Meter",        bill.get("meter_label") or "—"),
        ("RFID cards",   ", ".join(flat.get("rfid_uids") or []) or "—"),
    ]))
    el.append(Spacer(1, 5*mm))

    # Usage
    el += [_section(f"Usage — {_kwh(flat['units_consumed'])} kWh"), Spacer(1, 2*mm)]
    rows = [["Date", "Start", "End", "kWh", ""]]
    for s in sessions:
        rows.append([s["ended_at"].strftime("%d %b %Y"),
                     s["started_at"].strftime("%H:%M") if s.get("started_at") else "—",
                     s["ended_at"].strftime("%H:%M"),
                     _kwh(s["units"]),
                     "Adjustment" if s["is_adjustment"] else ""])
    rows.append(["Total", "", "", _kwh(flat["units_consumed"]), ""])
    el.append(_table(rows, [40*mm, 30*mm, 30*mm, 30*mm, 40*mm], right_cols=(3,), bold_last=True))
    if Decimal(str(flat.get("adjustment_units") or 0)) > 0:
        el.append(Paragraph("Adjustment: charging from an earlier period whose record arrived after that bill was made.",
                            _S["label"]))
    el.append(Spacer(1, 5*mm))

    # Charges
    u        = Decimal(str(flat["units_consumed"]))
    ind_rate = Decimal(str(flat["indram_rate"]))
    el += [_section("Charges"), Spacer(1, 2*mm)]
    rows = [
        ["Description", "Units", "Rate", "Amount"],
        ["MSEB electricity — before taxes", _kwh(u), rs(bill["tariff"]), rs(flat["bill_excl_taxes"])],
        ["MSEB taxes", "", "", rs(flat["mseb_taxes"])],
        ["MSEB electricity — after taxes", _kwh(u), rs(bill["effective_rate"]), rs(flat["electricity_charges_incl_tax"])],
        ["Indram service — before GST", _kwh(u), rs(ind_rate), rs(flat["indram_charges"])],
        ["CGST 9%", "", "", rs(flat["indram_cgst"])],
        ["SGST 9%", "", "", rs(flat["indram_sgst"])],
        ["Indram service — after GST", _kwh(u), rs(ind_rate * (1 + 2 * GST_HALF_RATE)), rs(flat["indram_total"])],
    ]
    total = Decimal(str(flat["total_payable"]))
    if late_fee:
        rows.append(["Bill amount", "", "", rs(total)])
        rows.append([f"Late fee ({late_fee_pct}% of bill)", "", "", rs(late_fee)])
        total += late_fee
    el.append(_table(rows, [80*mm, 25*mm, 30*mm, 35*mm], right_cols=(1, 2, 3)))
    el += [Spacer(1, 2*mm), _total_bar("TOTAL PAYABLE", total),
           Paragraph(amount_in_words(total), _S["body"]), Spacer(1, 5*mm)]

    # Payment
    payment = [_section("Payment"), Spacer(1, 2*mm)]
    payment += [Paragraph(line, _S["body"]) for line in _payment_lines(society)]
    payment.append(Paragraph(f"<b>Pay by:</b> {_d(bill['due_date'])}. Pay {society['name']}, not Indram.", _S["body"]))
    el += [KeepTogether(payment), Spacer(1, 5*mm)]

    el += [KeepTogether([_section("MSEB bill reference"), Spacer(1, 2*mm), _mseb_reference(bill)])]
    _build(buffer, el, "Computer-generated bill. For queries contact your society admin.")
    return buffer.getvalue()


# ── 2. Society admin's bills ──────────────────────────────────────────

SOCIETY_BILL_TITLES = {
    "society": "Society Total — MSEB + Indram",
    "mseb":    "MSEB Electricity Total",
    "indram":  "Indram Service Total (incl. 18% GST)",
}


def generate_society_bill_pdf(kind: str, society: dict, bill: dict, flats: list[dict],
                              letterhead: bytes | None = None) -> bytes:
    """kind: "society" (on letterhead, no payment details) | "mseb" | "indram"."""
    buffer = io.BytesIO()
    el = _letterhead(letterhead if kind == "society" else None, society["name"], society.get("address"))
    el += [Paragraph(SOCIETY_BILL_TITLES[kind], _S["title"]), Spacer(1, 3*mm)]
    el.append(_info_grid([
        ("Society",      society["name"]),
        ("Meter",        bill.get("meter_label") or "—"),
        ("Bill period",  _period(bill["period_from"], bill["period_till"])),
        ("Flats billed", str(len(flats))),
        ("Due date",     _d(bill["due_date"])),
        ("Units",        f"{_kwh(sum(Decimal(str(f['units_consumed'])) for f in flats))} kWh"),
    ]))
    el.append(Spacer(1, 5*mm))

    def col(f, key):
        return Decimal(str(f[key]))

    if kind == "society":
        head = ["Bill No.", "Flat", "kWh", "MSEB", "Indram + GST", "Total"]
        keys = ["electricity_charges_incl_tax", "indram_total", "total_payable"]
        widths = [32*mm, 22*mm, 22*mm, 30*mm, 32*mm, 32*mm]
    elif kind == "mseb":
        head = ["Bill No.", "Flat", "kWh", "Before taxes", "MSEB taxes", "After taxes"]
        keys = ["bill_excl_taxes", "mseb_taxes", "electricity_charges_incl_tax"]
        widths = [32*mm, 22*mm, 22*mm, 32*mm, 30*mm, 32*mm]
    else:
        head = ["Bill No.", "Flat", "kWh", "Before GST", "GST 18%", "After GST"]
        keys = ["indram_charges", None, "indram_total"]
        widths = [32*mm, 22*mm, 22*mm, 32*mm, 30*mm, 32*mm]

    def val(f, key):
        return col(f, "indram_cgst") + col(f, "indram_sgst") if key is None else col(f, key)

    rows = [head]
    totals = [Decimal("0")] * 4
    for f in flats:
        vals = [col(f, "units_consumed")] + [val(f, k) for k in keys]
        totals = [a + b for a, b in zip(totals, vals)]
        rows.append([f.get("bill_number") or "DRAFT", f["flat_number"], _kwh(vals[0])] + [rs(v) for v in vals[1:]])
    rows.append(["Total", "", _kwh(totals[0])] + [rs(v) for v in totals[1:]])
    el.append(_table(rows, widths, right_cols=(2, 3, 4, 5), bold_last=True))
    el += [Spacer(1, 3*mm), _total_bar("TOTAL", totals[3], _GREEN if kind == "indram" else _TOTAL),
           Paragraph(amount_in_words(totals[3]), _S["body"]), Spacer(1, 5*mm)]

    if kind == "indram":
        el.append(Paragraph("Indram's GST tax invoice for this amount is sent separately.", _S["body"]))
    if kind in ("society", "mseb"):
        el += [KeepTogether([_section("MSEB bill reference"), Spacer(1, 2*mm), _mseb_reference(bill)])]
    _build(buffer, el, "Summary for the society admin.")
    return buffer.getvalue()


# ── 3. Indram GST tax invoice ─────────────────────────────────────────
# Laid out like Indram's own invoices (INV-000001): bordered page, company header, invoice
# details + place of supply, Bill To, HSN/SAC line items with CGST/SGST per line, totals
# rounded to the rupee, total in words, notes, authorized signature. DejaVu Sans for the ₹ sign.

_FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
pdfmetrics.registerFont(TTFont("DejaVu", str(_FONT_DIR / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(_FONT_DIR / "DejaVuSans-Bold.ttf")))

_INV_W    = 180 * mm
_INV_LINE = colors.HexColor("#9ca3af")
_INV_HEAD = colors.HexColor("#f3f4f6")

GST_STATES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh",
    "05": "Uttarakhand", "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur",
    "15": "Mizoram", "16": "Tripura", "17": "Meghalaya", "18": "Assam", "19": "West Bengal",
    "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra", "29": "Karnataka", "30": "Goa",
    "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry",
    "35": "Andaman and Nicobar Islands", "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh",
}


def _ps(name, size=8.5, bold=False, align=TA_LEFT, color=colors.black, leading=None):
    return ParagraphStyle(name, fontName="DejaVu-Bold" if bold else "DejaVu", fontSize=size,
                          leading=leading or size * 1.3, alignment=align, textColor=color)


_I = {
    "company": _ps("i-company", 13, bold=True, leading=16),
    "small":   _ps("i-small", 7.5, leading=9.5),
    "title":   _ps("i-title", 22, align=TA_RIGHT, leading=26),
    "label":   _ps("i-label", 8),
    "value":   _ps("i-value", 8, bold=True),
    "th":      _ps("i-th", 7.5, bold=True),
    "th_r":    _ps("i-th-r", 7.5, bold=True, align=TA_RIGHT),
    "th_c":    _ps("i-th-c", 7.5, bold=True, align=TA_CENTER),
    "td":      _ps("i-td", 7.5),
    "td_r":    _ps("i-td-r", 7.5, align=TA_RIGHT),
    "td_sub":  _ps("i-td-sub", 6.5, color=colors.HexColor("#6b7280")),
    "billto":  _ps("i-billto", 9.5, bold=True),
    "tot_l":   _ps("i-tot-l", 8, align=TA_RIGHT),
    "tot_r":   _ps("i-tot-r", 8, align=TA_RIGHT),
    "big_l":   _ps("i-big-l", 9, bold=True, align=TA_RIGHT),
    "big_r":   _ps("i-big-r", 9, bold=True, align=TA_RIGHT),
    "words":   _ps("i-words", 8, bold=True),
    "sign":    _ps("i-sign", 8, align=TA_CENTER),
}


def _n(amount) -> str:
    return _indian(amount)


def _qty(units) -> str:
    u = Decimal(str(units))
    return f"{u:.2f}" if u == u.quantize(Decimal("0.01")) else f"{u:.3f}"


def _dmy(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def place_of_supply(society_gstin: str | None, default_code: str) -> str:
    code = society_gstin[:2] if society_gstin and society_gstin[:2].isdigit() else default_code
    return f"{GST_STATES.get(code, '')} ({code})".strip()


def generate_indram_invoice_pdf(indram: dict, society: dict, invoice: dict) -> bytes:
    """
    indram  — legal_name, address (\\n-separated lines), gstin, phone, email, state_code, item, sac, notes
    society — name, address, gstin
    invoice — invoice_number, issued_on, period_from, period_till, due_date, meter_label,
              total_units, indram_rate, total_indram_amount, late_fee, late_fee_pct,
              cgst, sgst, rounding, total_payable, payment_status, replaces_number (optional)
    """
    buffer = io.BytesIO()
    line = _INV_LINE

    # Header: company block + TAX INVOICE
    company = [Paragraph(escape(indram["legal_name"]), _I["company"])]
    for text in [*filter(None, (indram.get("address") or "").split("\n")),
                 f"GSTIN {indram['gstin']}" if indram.get("gstin") else None,
                 indram.get("phone"), indram.get("email")]:
        if text:
            company.append(Paragraph(escape(text), _I["small"]))
    header = Table([[company, Paragraph("TAX INVOICE", _I["title"])]], colWidths=[_INV_W * 0.6, _INV_W * 0.4])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (0, 0), "TOP"), ("VALIGN", (1, 0), (1, 0), "BOTTOM"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                                ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                                ("LINEBELOW", (0, 0), (-1, 0), 0.75, line)]))

    # Invoice details | place of supply
    def kv(rows):
        t = Table([[Paragraph(k, _I["label"]), Paragraph(f": {escape(v)}", _I["value"])] for k, v in rows],
                  colWidths=[_INV_W * 0.22, _INV_W * 0.28])
        t.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 0.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5),
                               ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        return t
    details = Table([[
        kv([("#", invoice["invoice_number"]), ("Invoice Date", _dmy(invoice["issued_on"])),
            ("Terms", f"Due by {_dmy(invoice['due_date'])}"), ("Due Date", _dmy(invoice["due_date"])),
            ("Service Period", f"{_dmy(invoice['period_from'])} – {_dmy(invoice['period_till'])}")]),
        kv([("Place Of Supply", place_of_supply(society.get("gstin"), indram.get("state_code", "27")))]),
    ]], colWidths=[_INV_W / 2, _INV_W / 2])
    details.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEAFTER", (0, 0), (0, 0), 0.75, line),
                                 ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 4),
                                 ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LINEBELOW", (0, 0), (-1, 0), 0.75, line)]))

    # Bill To
    bill_to = [Paragraph(escape(society["name"]), _I["billto"])]
    for text in [*filter(None, (society.get("address") or "").split("\n")),
                 f"GSTIN {society['gstin']}" if society.get("gstin") else None]:
        if text:
            bill_to.append(Paragraph(escape(text), _I["small"]))
    billto = Table([[Paragraph("Bill To", _I["th"])], [bill_to]], colWidths=[_INV_W])
    billto.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), _INV_HEAD), ("LINEBELOW", (0, 0), (0, 0), 0.75, line),
                                ("LINEBELOW", (0, 1), (0, 1), 0.75, line), ("LEFTPADDING", (0, 0), (-1, -1), 6),
                                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))

    # Line items: the service, then the late fee once flagged
    charges = Decimal(str(invoice["total_indram_amount"]))
    late    = Decimal(str(invoice.get("late_fee") or 0))
    lines   = [(Paragraph(escape(indram.get("item") or "Charger Maintenance"), _I["td"]),
                Paragraph(escape(f"{invoice.get('meter_label') or ''} · units in kWh"), _I["td_sub"]),
                _qty(invoice["total_units"]), _n(invoice["indram_rate"]), charges)]
    if late > 0:
        lines.append((Paragraph(f"Late fee ({Decimal(str(invoice['late_fee_pct'])).normalize()}% of charges)", _I["td"]),
                      None, "1.00", _n(late), late))
    rows = [
        [Paragraph("#", _I["th_c"]), Paragraph("Item &amp; Description", _I["th"]), Paragraph("HSN<br/>/SAC", _I["th"]),
         Paragraph("Qty", _I["th_r"]), Paragraph("Rate", _I["th_r"]), Paragraph("CGST", _I["th_c"]), "",
         Paragraph("SGST", _I["th_c"]), "", Paragraph("Amount", _I["th_r"])],
        ["", "", "", "", "", Paragraph("%", _I["th_r"]), Paragraph("Amt", _I["th_r"]),
         Paragraph("%", _I["th_r"]), Paragraph("Amt", _I["th_r"]), ""],
    ]
    for i, (name, sub, qty, rate, amount) in enumerate(lines, start=1):
        half = round2(amount * GST_HALF_RATE)
        rows.append([Paragraph(str(i), _I["th_c"].clone("c", fontName="DejaVu")), [name, sub] if sub else name,
                     Paragraph(escape(indram.get("sac") or ""), _I["td"]), Paragraph(qty, _I["td_r"]),
                     Paragraph(rate, _I["td_r"]), Paragraph("9%", _I["td_r"]), Paragraph(_n(half), _I["td_r"]),
                     Paragraph("9%", _I["td_r"]), Paragraph(_n(half), _I["td_r"]), Paragraph(_n(amount), _I["td_r"])])
    widths = [m * mm for m in (8, 50, 17, 16, 17, 11, 15, 11, 15, 20)]
    items = Table(rows, colWidths=widths, repeatRows=2)
    items.setStyle(TableStyle([
        ("SPAN", (0, 0), (0, 1)), ("SPAN", (1, 0), (1, 1)), ("SPAN", (2, 0), (2, 1)), ("SPAN", (3, 0), (3, 1)),
        ("SPAN", (4, 0), (4, 1)), ("SPAN", (5, 0), (6, 0)), ("SPAN", (7, 0), (8, 0)), ("SPAN", (9, 0), (9, 1)),
        ("BACKGROUND", (0, 0), (-1, 1), _INV_HEAD), ("VALIGN", (0, 0), (-1, 1), "BOTTOM"),
        ("VALIGN", (0, 2), (-1, -1), "TOP"),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, line), ("LINEBELOW", (0, -1), (-1, -1), 0.75, line),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    # Totals | words + notes, then the signature box under the totals
    total    = Decimal(str(invoice["total_payable"]))
    rounding = Decimal(str(invoice.get("rounding") or 0))
    balance  = Decimal("0") if invoice.get("payment_status") == "paid" else total
    sums = [("Sub Total", _n(charges + late), "tot"), ("CGST9 (9%)", _n(invoice["cgst"]), "tot"),
            ("SGST9 (9%)", _n(invoice["sgst"]), "tot")]
    if rounding:
        sums.append(("Rounding", _n(rounding), "tot"))
    sums += [("Total", f"₹{_n(total)}", "big"), ("Balance Due", f"₹{_n(balance)}", "big")]
    totals = Table([[Paragraph(k, _I[f"{s}_l"]), Paragraph(v, _I[f"{s}_r"])] for k, v, s in sums],
                   colWidths=[_INV_W * 0.3, _INV_W * 0.2 - 12])
    totals.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("LINEABOVE", (0, -2), (-1, -2), 0.5, line)]))
    notes = [Paragraph("Total In Words", _I["label"]),
             Paragraph(escape(amount_in_words(total, "Indian Rupee")), _I["words"]), Spacer(1, 4 * mm),
             Paragraph("Notes", _I["label"]), Paragraph(escape(indram.get("notes") or ""), _I["td"])]
    if invoice.get("replaces_number"):
        notes.append(Paragraph(escape(f"This invoice replaces cancelled invoice no. {invoice['replaces_number']}."), _I["td"]))
    summary = Table([[notes, totals], ["", Paragraph("Authorized Signature", _I["sign"])]],
                    colWidths=[_INV_W / 2, _INV_W / 2], rowHeights=[None, 30 * mm])
    summary.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, 0), "TOP"), ("VALIGN", (1, 1), (1, 1), "BOTTOM"),
        ("LINEBEFORE", (1, 0), (1, 1), 0.75, line), ("LINEBELOW", (1, 0), (1, 0), 0.75, line),
        ("LINEBELOW", (1, 1), (1, 1), 0.75, line),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    def page(canvas, doc):   # the bordered page + page number, as on Indram's invoices
        canvas.saveState()
        canvas.setStrokeColor(line)
        canvas.setLineWidth(0.75)
        canvas.rect(doc.leftMargin, doc.bottomMargin, doc.width, doc.height)
        canvas.setFont("DejaVu", 7)
        canvas.setFillColor(colors.grey)
        canvas.drawRightString(doc.leftMargin + doc.width, doc.bottomMargin - 5 * mm, str(doc.page))
        canvas.restoreState()

    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=12 * mm, bottomMargin=14 * mm)
    doc.build([header, details, billto, items, summary], onFirstPage=page, onLaterPages=page)
    return buffer.getvalue()


# ── 4. Resident receipt ───────────────────────────────────────────────

def generate_resident_receipt_pdf(society: dict, bill: dict, flat: dict, letterhead: bytes | None = None) -> bytes:
    """Receipt on the society letterhead. Includes the late fee when the bill had been marked unpaid."""
    buffer = io.BytesIO()
    el = _letterhead(letterhead, society["name"], society.get("address"))
    el += [Paragraph("Payment Receipt", _S["title"]), Spacer(1, 3*mm)]

    bill_amount = Decimal(str(flat["total_payable"]))
    late        = Decimal(str(flat.get("late_fee") or 0))
    paid_on     = flat["paid_at"].astimezone(IST).date() if flat.get("paid_at") else date.today()
    el.append(_info_grid([
        ("Receipt No.",   f"R-{flat['bill_number']}"),
        ("Received on",   _d(paid_on)),
        ("Against bill",  flat["bill_number"]),
        ("Received from", flat.get("owner_name") or "—"),
        ("Flat",          flat["flat_number"]),
        ("Bill period",   _period(bill["period_from"], bill["period_till"])),
    ]))
    el.append(Spacer(1, 5*mm))

    rows = [["Description", "Amount"],
            [f"EV charging bill {flat['bill_number']} ({_kwh(flat['units_consumed'])} kWh)", rs(bill_amount)]]
    if late > 0:
        rows.append([f"Late fee ({flat.get('late_fee_pct')}%)", rs(late)])
    el.append(_table(rows, [_WIDTH - 45*mm, 45*mm], right_cols=(1,)))
    el += [Spacer(1, 2*mm), _total_bar("AMOUNT RECEIVED", bill_amount + late, _GREEN),
           Paragraph(amount_in_words(bill_amount + late), _S["body"]), Spacer(1, 6*mm),
           Paragraph(f"Received with thanks by {society['name']}. This bill is fully paid.", _S["body"])]
    _build(buffer, el, "Computer-generated receipt.")
    return buffer.getvalue()


# ── 5. Indram receipt ─────────────────────────────────────────────────

def generate_indram_receipt_pdf(indram: dict, society: dict, invoice: dict, paid_on: date) -> bytes:
    """Receipt for a paid Indram invoice. `invoice` as for generate_indram_invoice_pdf."""
    buffer = io.BytesIO()
    el = [Paragraph(indram["legal_name"], _S["title"])]
    if indram.get("address"):
        el.append(Paragraph(indram["address"], _S["sub"]))
    if indram.get("gstin"):
        el.append(Paragraph(f"GSTIN: {indram['gstin']}", _S["sub"]))
    el += [Spacer(1, 3*mm), HRFlowable(width="100%", thickness=1.5, color=_GREEN), Spacer(1, 3*mm),
           Paragraph("Payment Receipt", _S["title"]), Spacer(1, 3*mm)]
    el.append(_info_grid([
        ("Receipt No.",    f"R-{invoice['invoice_number']}"),
        ("Received on",    _d(paid_on)),
        ("Against invoice", invoice["invoice_number"]),
        ("Received from",  society["name"]),
        ("Society GSTIN",  society.get("gstin") or "—"),
        ("Service period", _period(invoice["period_from"], invoice["period_till"])),
    ]))
    el.append(Spacer(1, 5*mm))

    late = Decimal(str(invoice.get("late_fee") or 0))
    rows = [["Description", "Amount"],
            [f"Indram platform service ({_kwh(invoice['total_units'])} kWh)", rs(invoice["total_indram_amount"])]]
    if late > 0:
        rows.append([f"Late fee ({invoice['late_fee_pct']}%)", rs(late)])
    rows += [["CGST 9%", rs(invoice["cgst"])], ["SGST 9%", rs(invoice["sgst"])]]
    el.append(_table(rows, [_WIDTH - 45*mm, 45*mm], right_cols=(1,)))
    el += [Spacer(1, 2*mm), _total_bar("AMOUNT RECEIVED", invoice["total_payable"], _GREEN),
           Paragraph(amount_in_words(Decimal(str(invoice["total_payable"]))), _S["body"]), Spacer(1, 6*mm),
           Paragraph(f"Received with thanks from {society['name']}. This invoice is fully paid.", _S["body"])]
    _build(buffer, el, "Computer-generated receipt.")
    return buffer.getvalue()
