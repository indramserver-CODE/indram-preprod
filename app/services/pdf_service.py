"""
app/services/pdf_service.py
----------------------------
Two PDF generators:
  1. generate_bill_pdf        — individual flat EV charging bill
  2. generate_indram_invoice_pdf — Indram platform invoice to society admin
"""

import io
from datetime import date
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT


# ─────────────────────────────────────────────────────────────────────
#  Shared colour palette
# ─────────────────────────────────────────────────────────────────────
_PRIMARY   = colors.HexColor("#1a3c5e")
_ACCENT    = colors.HexColor("#4f86f7")
_GREEN     = colors.HexColor("#276749")
_LIGHT_BG  = colors.HexColor("#f0f4f8")
_RED_TOTAL = colors.HexColor("#c53030")
_DARK_HDR  = colors.HexColor("#2d3748")


# ─────────────────────────────────────────────────────────────────────
#  1. Flat bill PDF (unchanged)
# ─────────────────────────────────────────────────────────────────────

def generate_bill_pdf(
    society_name:                str,
    flat_number:                 str,
    owner_name:                  str | None,
    billing_month:               date,
    due_date:                    date,
    bill_number:                 str,
    prev_reading:                Decimal,
    curr_reading:                Decimal,
    units_consumed:              Decimal,
    effective_unit_rate:         Decimal,
    tariff:                      Decimal,
    bill_excl_taxes:             Decimal,
    mseb_taxes:                  Decimal,
    electricity_charges_incl_tax: Decimal,
    indram_charges:              Decimal,
    total_payable:               Decimal,
    payment_instructions:        str = "",
    contact_info:                str = "",
) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=20*mm,  bottomMargin=20*mm,
    )
    styles   = getSampleStyleSheet()
    elements = []

    title_style   = ParagraphStyle("title",   parent=styles["Normal"], fontSize=20,
                                   textColor=_PRIMARY, fontName="Helvetica-Bold", alignment=TA_CENTER)
    sub_style     = ParagraphStyle("sub",     parent=styles["Normal"], fontSize=10,
                                   textColor=colors.grey, alignment=TA_CENTER)
    label_style   = ParagraphStyle("label",   parent=styles["Normal"], fontSize=9,
                                   textColor=colors.grey, fontName="Helvetica")
    value_style   = ParagraphStyle("value",   parent=styles["Normal"], fontSize=10,
                                   textColor=_PRIMARY, fontName="Helvetica-Bold")
    section_style = ParagraphStyle("section", parent=styles["Normal"], fontSize=11,
                                   textColor=colors.white, fontName="Helvetica-Bold")
    footer_style  = ParagraphStyle("footer",  parent=styles["Normal"], fontSize=8,
                                   textColor=colors.grey, alignment=TA_CENTER)

    elements.append(Paragraph("⚡ EV Charging Bill", title_style))
    elements.append(Paragraph(society_name, sub_style))
    elements.append(Spacer(1, 4*mm))
    elements.append(HRFlowable(width="100%", thickness=2, color=_ACCENT))
    elements.append(Spacer(1, 4*mm))

    month_str = billing_month.strftime("%B %Y")
    info_data = [
        [Paragraph("<b>Flat No.</b>",  label_style), Paragraph("<b>Owner</b>",      label_style),
         Paragraph("<b>Bill Month</b>",label_style), Paragraph("<b>Bill No.</b>",   label_style),
         Paragraph("<b>Due Date</b>",  label_style)],
        [Paragraph(flat_number,                    value_style), Paragraph(owner_name or "—",        value_style),
         Paragraph(month_str,                      value_style), Paragraph(bill_number,              value_style),
         Paragraph(due_date.strftime("%d %b %Y"),  value_style)],
    ]
    info_table = Table(info_data, colWidths=[30*mm, 45*mm, 35*mm, 35*mm, 30*mm])
    info_table.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), _LIGHT_BG),
        ("GRID",          (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 6*mm))

    def _section_hdr(title):
        t = Table([[Paragraph(title, section_style)]], colWidths=[175*mm])
        t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),_PRIMARY),
                                ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
                                ("LEFTPADDING",(0,0),(-1,-1),8)]))
        return t

    elements.append(_section_hdr("Meter &amp; Consumption Details"))
    elements.append(Spacer(1, 2*mm))
    meter_data = [
        ["Previous Reading (kWh)",       f"{prev_reading:.4f}"],
        ["Current Reading (kWh)",        f"{curr_reading:.4f}"],
        ["Units Consumed (kWh)",         f"{units_consumed:.4f}"],
        ["Effective Unit Rate (₹/kWh)",  f"₹ {effective_unit_rate:.4f}  (incl. all taxes)"],
    ]
    mt = Table(meter_data, colWidths=[100*mm, 75*mm])
    mt.setStyle(TableStyle([
        ("ROWBACKGROUNDS",(0,0),(-1,-1),[colors.white,_LIGHT_BG]),
        ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#e2e8f0")),
        ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
        ("LEFTPADDING",(0,0),(-1,-1),8),
        ("FONTNAME",(1,0),(1,-1),"Helvetica-Bold"),
        ("FONTNAME",(0,2),(0,2),"Helvetica-Bold"),("TEXTCOLOR",(0,2),(1,2),_PRIMARY),
    ]))
    elements.append(mt)
    elements.append(Spacer(1, 6*mm))

    elements.append(_section_hdr("Bill Amount Bifurcation"))
    elements.append(Spacer(1, 2*mm))
    bifur_data = [
        ["Description",                           "Calculation",                                           "Amount (₹)"],
        ["Base Electricity Charges (excl. tax)",  f"{units_consumed:.4f} × ₹{tariff:.4f}",                f"₹ {bill_excl_taxes:.2f}"],
        ["MSEB Taxes & Surcharges",               "(incl. rate − base rate) × units",                     f"₹ {mseb_taxes:.2f}"],
        ["Electricity Charges (incl. all taxes)", f"{units_consumed:.4f} × ₹{effective_unit_rate:.4f}",   f"₹ {electricity_charges_incl_tax:.2f}"],
        ["Indram Platform Charges",               f"{units_consumed:.4f} × ₹{indram_charges/units_consumed if units_consumed else 0:.4f}", f"₹ {indram_charges:.2f}"],
    ]
    bt = Table(bifur_data, colWidths=[75*mm, 65*mm, 35*mm])
    bt.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),_DARK_HDR),("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,_LIGHT_BG]),
        ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#e2e8f0")),
        ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
        ("LEFTPADDING",(0,0),(-1,-1),8),("ALIGN",(2,0),(2,-1),"RIGHT"),
    ]))
    elements.append(bt)
    elements.append(Spacer(1, 2*mm))
    total_data = [["TOTAL AMOUNT PAYABLE", f"₹ {total_payable:.2f}"]]
    tt = Table(total_data, colWidths=[140*mm, 35*mm])
    tt.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),_RED_TOTAL),("TEXTCOLOR",(0,0),(-1,-1),colors.white),
        ("FONTNAME",(0,0),(-1,-1),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),12),
        ("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8),
        ("LEFTPADDING",(0,0),(-1,-1),8),("ALIGN",(1,0),(1,0),"RIGHT"),
    ]))
    elements.append(tt)
    elements.append(Spacer(1, 8*mm))

    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0")))
    elements.append(Spacer(1, 3*mm))
    if payment_instructions:
        elements.append(Paragraph(f"<b>Payment Instructions:</b> {payment_instructions}", footer_style))
        elements.append(Spacer(1, 2*mm))
    if contact_info:
        elements.append(Paragraph(f"<b>Contact:</b> {contact_info}", footer_style))
        elements.append(Spacer(1, 2*mm))
    elements.append(Paragraph(
        f"This is a computer-generated bill. For queries contact your society admin. "
        f"Generated on {date.today().strftime('%d %b %Y')}.",
        footer_style,
    ))

    doc.build(elements)
    return buffer.getvalue()


# ─────────────────────────────────────────────────────────────────────
#  2. Indram platform invoice PDF
# ─────────────────────────────────────────────────────────────────────

def generate_indram_invoice_pdf(
    society_name:        str,
    society_address:     str | None,
    billing_month:       date,
    due_date:            date,
    invoice_number:      str,
    total_indram_amount: Decimal,
    total_units:         Decimal,
    meter_breakdown:     list[dict],   # [{meter_number, meter_label, units_billed, indram_amount}]
    indram_rate:         Decimal,
) -> bytes:
    """
    Generate a professional platform invoice PDF from Indram to the society.

    meter_breakdown is a list of dicts with keys:
        meter_number, meter_label, units_billed, indram_amount
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=20*mm, bottomMargin=20*mm,
    )
    styles   = getSampleStyleSheet()
    elements = []

    # ── Styles ───────────────────────────────────────────────
    title_style   = ParagraphStyle("inv_title",   parent=styles["Normal"], fontSize=22,
                                    textColor=_PRIMARY, fontName="Helvetica-Bold", alignment=TA_CENTER)
    tagline_style = ParagraphStyle("inv_tagline", parent=styles["Normal"], fontSize=10,
                                    textColor=colors.grey, alignment=TA_CENTER)
    label_style   = ParagraphStyle("inv_label",   parent=styles["Normal"], fontSize=9,
                                    textColor=colors.grey)
    value_style   = ParagraphStyle("inv_value",   parent=styles["Normal"], fontSize=10,
                                    textColor=_PRIMARY, fontName="Helvetica-Bold")
    section_style = ParagraphStyle("inv_section", parent=styles["Normal"], fontSize=11,
                                    textColor=colors.white, fontName="Helvetica-Bold")
    footer_style  = ParagraphStyle("inv_footer",  parent=styles["Normal"], fontSize=8,
                                    textColor=colors.grey, alignment=TA_CENTER)
    note_style    = ParagraphStyle("inv_note",    parent=styles["Normal"], fontSize=9,
                                    textColor=colors.HexColor("#4a5568"))

    month_str = billing_month.strftime("%B %Y")

    # ── Header ───────────────────────────────────────────────
    elements.append(Paragraph("⚡ INDRAM", title_style))
    elements.append(Paragraph("EV Charging Management Platform", tagline_style))
    elements.append(Spacer(1, 3*mm))
    elements.append(HRFlowable(width="100%", thickness=2, color=_ACCENT))
    elements.append(Spacer(1, 5*mm))

    # Invoice title
    inv_title_style = ParagraphStyle("inv_h", parent=styles["Normal"], fontSize=14,
                                      textColor=_PRIMARY, fontName="Helvetica-Bold", alignment=TA_CENTER)
    elements.append(Paragraph(f"PLATFORM SERVICE INVOICE — {month_str.upper()}", inv_title_style))
    elements.append(Spacer(1, 5*mm))

    # From / To / Invoice details grid
    from_lines = "INDRAM Technologies\nEV Charging Management Platform\nIndia\nplatform@indram.in"
    to_lines   = f"{society_name}\n{society_address or 'India'}"

    from_to_data = [
        [Paragraph("<b>From</b>", label_style),   Paragraph("<b>Bill To</b>", label_style),
         Paragraph("<b>Invoice No.</b>", label_style), Paragraph("<b>Due Date</b>", label_style)],
        [Paragraph(from_lines.replace("\n","<br/>"), note_style),
         Paragraph(to_lines.replace("\n","<br/>"),   note_style),
         Paragraph(invoice_number, value_style),
         Paragraph(due_date.strftime("%d %b %Y"), value_style)],
    ]
    ft = Table(from_to_data, colWidths=[45*mm, 55*mm, 45*mm, 30*mm])
    ft.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), _LIGHT_BG),
        ("GRID",          (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
    ]))
    elements.append(ft)
    elements.append(Spacer(1, 6*mm))

    # ── Section: Meter-wise Breakdown ─────────────────────────
    def _section_hdr(title):
        t = Table([[Paragraph(title, section_style)]], colWidths=[175*mm])
        t.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,-1),_PRIMARY),
            ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
            ("LEFTPADDING",(0,0),(-1,-1),8),
        ]))
        return t

    elements.append(_section_hdr("Meter-wise Service Charge Breakdown"))
    elements.append(Spacer(1, 2*mm))

    breakdown_header = [
        Paragraph("<b>Meter No.</b>",       label_style),
        Paragraph("<b>Meter Label</b>",     label_style),
        Paragraph("<b>Units Billed (kWh)</b>", label_style),
        Paragraph("<b>Rate (₹/kWh)</b>",    label_style),
        Paragraph("<b>Indram Charges (₹)</b>", label_style),
    ]
    breakdown_rows = [breakdown_header]
    for m in meter_breakdown:
        breakdown_rows.append([
            m["meter_number"],
            m["meter_label"],
            f"{Decimal(str(m['units_billed'])):.4f}",
            f"₹ {indram_rate:.4f}",
            f"₹ {Decimal(str(m['indram_amount'])):.2f}",
        ])

    # Totals row
    breakdown_rows.append([
        Paragraph("<b>TOTAL</b>", value_style), "",
        Paragraph(f"<b>{total_units:.4f}</b>", value_style), "",
        Paragraph(f"<b>₹ {total_indram_amount:.2f}</b>", value_style),
    ])

    bdt = Table(breakdown_rows, colWidths=[35*mm, 45*mm, 38*mm, 27*mm, 30*mm])
    bdt.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), _DARK_HDR),
        ("TEXTCOLOR",     (0,0), (-1,0), colors.white),
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
        ("ROWBACKGROUNDS",(0,1), (-1,-2), [colors.white, _LIGHT_BG]),
        ("BACKGROUND",    (0,-1),(-1,-1), _LIGHT_BG),
        ("FONTNAME",      (0,-1),(-1,-1), "Helvetica-Bold"),
        ("GRID",          (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("ALIGN",         (2,0), (4,-1), "RIGHT"),
    ]))
    elements.append(bdt)
    elements.append(Spacer(1, 4*mm))

    # ── Total payable ─────────────────────────────────────────
    total_data = [["TOTAL AMOUNT PAYABLE TO INDRAM", f"₹ {total_indram_amount:.2f}"]]
    tt = Table(total_data, colWidths=[140*mm, 35*mm])
    tt.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),_GREEN),("TEXTCOLOR",(0,0),(-1,-1),colors.white),
        ("FONTNAME",(0,0),(-1,-1),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),12),
        ("TOPPADDING",(0,0),(-1,-1),10),("BOTTOMPADDING",(0,0),(-1,-1),10),
        ("LEFTPADDING",(0,0),(-1,-1),8),("ALIGN",(1,0),(1,0),"RIGHT"),
    ]))
    elements.append(tt)
    elements.append(Spacer(1, 8*mm))

    # ── Payment instructions ──────────────────────────────────
    elements.append(_section_hdr("Payment Instructions"))
    elements.append(Spacer(1, 2*mm))

    payment_data = [
        ["Payment Method", "Bank Transfer / UPI"],
        ["Account Name",   "INDRAM Technologies (Placeholder)"],
        ["Account Number", "XXXX-XXXX-XXXX (Placeholder)"],
        ["IFSC Code",      "XXXXXXXXX (Placeholder)"],
        ["UPI ID",         "indram@bank (Placeholder)"],
        ["Reference",      invoice_number],
    ]
    pt = Table(payment_data, colWidths=[60*mm, 115*mm])
    pt.setStyle(TableStyle([
        ("ROWBACKGROUNDS",(0,0),(-1,-1),[colors.white,_LIGHT_BG]),
        ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#e2e8f0")),
        ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
        ("LEFTPADDING",(0,0),(-1,-1),8),
        ("FONTNAME",(0,0),(0,-1),"Helvetica-Bold"),
    ]))
    elements.append(pt)
    elements.append(Spacer(1, 8*mm))

    # ── Footer ────────────────────────────────────────────────
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0")))
    elements.append(Spacer(1, 3*mm))
    elements.append(Paragraph(
        "This is a computer-generated invoice from INDRAM platform. "
        "For queries contact platform@indram.in. "
        f"Generated on {date.today().strftime('%d %b %Y')}.",
        footer_style,
    ))

    doc.build(elements)
    return buffer.getvalue()