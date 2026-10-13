"""
app/services/email_service.py
------------------------------
Sends emails via Gmail SMTP.
  - send_bill_email           — a flat's EV charging bill with PDF
  - send_society_bills_email  — the society admin's three bill summaries
  - send_indram_bill_email    — Indram GST tax invoice to the society admin
  - send_unpaid_email         — bill re-sent with late fee, service being disabled
  - send_receipt_email        — payment receipt
  - send_payment_reminder_email / send_invoice_reminder_email — 2 days before the due date
  - send_invoice_late_email   — Indram invoice re-sent with late fee
  - send_password_reset_email — password reset link
"""

import asyncio
import smtplib
import logging
from html import escape
from datetime import date
from decimal import Decimal
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

from app.config import settings

logger = logging.getLogger(__name__)


def _smtp_send(msg: MIMEMultipart, to_email: str) -> bool:
    """Shared SMTP send helper."""
    if not settings.GMAIL_USER or not settings.GMAIL_APP_PASSWORD:
        logger.warning("GMAIL credentials not configured — skipping email to %s", to_email)
        return False
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(settings.GMAIL_USER, settings.GMAIL_APP_PASSWORD)
            server.sendmail(settings.GMAIL_USER, to_email, msg.as_string())
        return True
    except Exception as e:
        logger.error("SMTP error | to=%s error=%s", to_email, e)
        return False


# ── Billing emails ─────────────────────────────────────────────────────

def _wrap(title: str, subtitle: str, body_html: str, color: str = "#1a3c5e") -> str:
    return f"""
    <html><body style="font-family:Arial,sans-serif;color:#2d3748;max-width:600px;margin:auto;">
      <div style="background:{color};padding:24px;border-radius:8px 8px 0 0;">
        <h2 style="color:white;margin:0;">{escape(title)}</h2>
        <p style="color:#e2e8f0;margin:4px 0 0;">{escape(subtitle)}</p>
      </div>
      <div style="background:#f7fafc;padding:24px;border-radius:0 0 8px 8px;">
        {body_html}
        <p style="color:#718096;font-size:13px;">This is an automated email.</p>
      </div>
    </body></html>
    """


def _rows(pairs: list[tuple[str, str]], total: tuple[str, str] | None = None, total_color: str = "#c53030") -> str:
    html = '<table style="width:100%;border-collapse:collapse;margin:16px 0;">'
    for i, (k, v) in enumerate(pairs):
        bg = ' style="background:#e2e8f0;"' if i % 2 == 0 else ""
        html += f'<tr{bg}><td style="padding:10px;font-weight:bold;">{escape(k)}</td><td style="padding:10px;">{escape(v)}</td></tr>'
    if total:
        html += (f'<tr style="background:{total_color};"><td style="padding:12px;font-weight:bold;color:white;">{escape(total[0])}</td>'
                 f'<td style="padding:12px;font-weight:bold;color:white;font-size:18px;">{escape(total[1])}</td></tr>')
    return html + "</table>"


def _replaces_note(new_no: str, old_no: str | None, what: str = "bill") -> str:
    if not old_no:
        return ""
    return (f'<p style="background:#fefcbf;padding:12px;border-radius:6px;"><strong>Please use this new {what} '
            f'(no. {escape(new_no)}) and ignore the earlier one (no. {escape(old_no)}).</strong></p>')


def _period(period_from: date, period_till: date) -> str:
    return f"{period_from:%d %b %Y} – {period_till:%d %b %Y}"


async def _send(subject: str, to_email: str, html: str, attachments: list[tuple[str, bytes]]) -> bool:
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"]    = settings.GMAIL_USER
    msg["To"]      = to_email
    msg.attach(MIMEText(html, "html"))
    for filename, pdf_bytes in attachments:
        part = MIMEApplication(pdf_bytes, _subtype="pdf")
        part.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(part)
    # smtplib blocks — keep it off the event loop so MQTT handling isn't stalled
    return await asyncio.to_thread(_smtp_send, msg, to_email)


async def send_bill_email(
    to_email: str, owner_name: str | None, flat_number: str, society_name: str,
    period_from: date, period_till: date, total_payable: Decimal, due_date: date,
    pdf_bytes: bytes, bill_number: str, replaces_bill_number: str | None = None,
) -> bool:
    body = (f"<p>Dear <strong>{escape(owner_name or 'Resident')}</strong>,</p>"
            + _replaces_note(bill_number, replaces_bill_number)
            + f"<p>Your EV charging bill for <strong>{_period(period_from, period_till)}</strong> is attached.</p>"
            + _rows([("Bill No.", bill_number), ("Flat", flat_number),
                     ("Bill period", _period(period_from, period_till)), ("Due date", f"{due_date:%d %b %Y}")],
                    ("TOTAL PAYABLE", f"Rs. {total_payable:,.2f}"))
            + f"<p>Please pay <strong>{escape(society_name)}</strong> using the payment details on the bill.</p>")
    ok = await _send(f"{society_name} — EV Charging Bill {bill_number} | Flat {flat_number}", to_email,
                     _wrap("EV Charging Bill", society_name, body), [(f"Bill_{bill_number}.pdf", pdf_bytes)])
    if ok:
        logger.info("Flat bill email sent | bill=%s to=%s", bill_number, to_email)
    return ok


async def send_society_bills_email(
    to_email: str, society_name: str, meter_label: str, period_from: date, period_till: date,
    total_flats: int, society_total: Decimal, attachments: list[tuple[str, bytes]],
    replaced: bool = False,
) -> bool:
    note = ("<p><strong>These bills replace the earlier bills for this period, which are cancelled.</strong></p>"
            if replaced else "")
    body = (note + f"<p>Bills for <strong>{escape(meter_label)}</strong>, {_period(period_from, period_till)}, "
            f"have been emailed to {total_flats} flats. Your three summaries are attached:</p>"
            "<ul><li>Society total (MSEB + Indram)</li><li>MSEB total</li><li>Indram total including 18% GST</li></ul>"
            + _rows([("Meter", meter_label), ("Flats billed", str(total_flats))],
                    ("SOCIETY TOTAL", f"Rs. {society_total:,.2f}")))
    ok = await _send(f"{society_name} — Bills sent for {meter_label}, {_period(period_from, period_till)}", to_email,
                     _wrap("Bills sent", society_name, body), attachments)
    if ok:
        logger.info("Society bills email sent | society=%s to=%s", society_name, to_email)
    return ok


async def send_indram_bill_email(
    to_email: str, society_name: str, period_from: date, period_till: date,
    total_payable: Decimal, due_date: date, invoice_number: str, pdf_bytes: bytes,
    replaces_invoice_number: str | None = None,
) -> bool:
    body = ("<p>Dear Society Admin,</p>"
            + _replaces_note(invoice_number, replaces_invoice_number, "invoice")
            + f"<p>Indram's GST tax invoice for <strong>{escape(society_name)}</strong> is attached.</p>"
            + _rows([("Invoice No.", invoice_number), ("Service period", _period(period_from, period_till)),
                     ("Due date", f"{due_date:%d %b %Y}")],
                    ("TOTAL PAYABLE TO INDRAM", f"Rs. {total_payable:,.2f}"), "#276749"))
    ok = await _send(f"Indram Tax Invoice {invoice_number} — {society_name}", to_email,
                     _wrap("Indram Tax Invoice", society_name, body, "#276749"),
                     [(f"Indram_Invoice_{invoice_number.replace('/', '-')}.pdf", pdf_bytes)])
    if ok:
        logger.info("Indram invoice email sent | invoice=%s to=%s", invoice_number, to_email)
    return ok


async def send_unpaid_email(
    to_email: str, owner_name: str | None, flat_number: str, society_name: str, bill_number: str,
    total_with_late_fee: Decimal, late_fee: Decimal, pdf_bytes: bytes,
) -> bool:
    body = (f"<p>Dear <strong>{escape(owner_name or 'Resident')}</strong>,</p>"
            f"<p>Your EV charging bill <strong>{escape(bill_number)}</strong> has not been paid, so your "
            "<strong>charging service is being disabled</strong> and a late fee has been added.</p>"
            + _rows([("Bill No.", bill_number), ("Flat", flat_number), ("Late fee", f"Rs. {late_fee:,.2f}")],
                    ("NOW PAYABLE", f"Rs. {total_with_late_fee:,.2f}"))
            + f"<p>Please pay <strong>{escape(society_name)}</strong> the amount above and contact your society admin. "
            "Charging will be switched back on once the payment is recorded. The updated bill is attached.</p>")
    ok = await _send(f"{society_name} — Unpaid EV charging bill {bill_number} | Flat {flat_number}", to_email,
                     _wrap("Bill unpaid — late fee added", society_name, body, "#c53030"),
                     [(f"Bill_{bill_number}_with_late_fee.pdf", pdf_bytes)])
    if ok:
        logger.info("Unpaid email sent | bill=%s to=%s", bill_number, to_email)
    return ok


async def send_receipt_email(
    to_email: str, owner_name: str | None, flat_number: str, society_name: str, bill_number: str,
    amount: Decimal, pdf_bytes: bytes,
) -> bool:
    body = (f"<p>Dear <strong>{escape(owner_name or 'Resident')}</strong>,</p>"
            f"<p>Thank you — your payment for bill <strong>{escape(bill_number)}</strong> has been received. "
            "Your receipt is attached.</p>"
            + _rows([("Bill No.", bill_number), ("Flat", flat_number)], ("AMOUNT RECEIVED", f"Rs. {amount:,.2f}"), "#276749"))
    ok = await _send(f"{society_name} — Payment receipt for bill {bill_number}", to_email,
                     _wrap("Payment received", society_name, body, "#276749"),
                     [(f"Receipt_{bill_number}.pdf", pdf_bytes)])
    if ok:
        logger.info("Receipt email sent | bill=%s to=%s", bill_number, to_email)
    return ok


async def send_payment_reminder_email(
    to_email: str, owner_name: str | None, flat_number: str, society_name: str, bill_number: str,
    total_payable: Decimal, due_date: date,
) -> bool:
    body = (f"<p>Dear <strong>{escape(owner_name or 'Resident')}</strong>,</p>"
            f"<p>Please pay your EV charging bill <strong>{escape(bill_number)}</strong> by "
            f"<strong>{due_date:%d %b %Y}</strong>. Services may be stopped if it is unpaid.</p>"
            + _rows([("Bill No.", bill_number), ("Flat", flat_number), ("Due date", f"{due_date:%d %b %Y}")],
                    ("AMOUNT DUE", f"Rs. {total_payable:,.2f}"))
            + f"<p>Pay <strong>{escape(society_name)}</strong> using the payment details on your bill. "
            "If you have already paid, please ignore this email.</p>")
    ok = await _send(f"{society_name} — Reminder: EV charging bill {bill_number} due {due_date:%d %b}", to_email,
                     _wrap("Payment reminder", society_name, body), [])
    if ok:
        logger.info("Payment reminder sent | bill=%s to=%s", bill_number, to_email)
    return ok


async def send_invoice_reminder_email(
    to_email: str, society_name: str, invoice_number: str, total_payable: Decimal, due_date: date,
) -> bool:
    body = ("<p>Dear Society Admin,</p>"
            f"<p>Indram invoice <strong>{escape(invoice_number)}</strong> is due on "
            f"<strong>{due_date:%d %b %Y}</strong>. A late fee applies if it is paid after the due date.</p>"
            + _rows([("Invoice No.", invoice_number), ("Due date", f"{due_date:%d %b %Y}")],
                    ("AMOUNT DUE", f"Rs. {total_payable:,.2f}"), "#276749")
            + "<p>If you have already paid, please ignore this email.</p>")
    ok = await _send(f"Reminder: Indram invoice {invoice_number} due {due_date:%d %b} — {society_name}", to_email,
                     _wrap("Invoice reminder", society_name, body, "#276749"), [])
    if ok:
        logger.info("Invoice reminder sent | invoice=%s to=%s", invoice_number, to_email)
    return ok


async def send_invoice_late_email(
    to_email: str, society_name: str, invoice_number: str, late_fee: Decimal,
    total_payable: Decimal, pdf_bytes: bytes,
) -> bool:
    body = ("<p>Dear Society Admin,</p>"
            f"<p>Indram invoice <strong>{escape(invoice_number)}</strong> has not been paid by its due date, "
            "so a late fee has been added. Services may be stopped if it remains unpaid.</p>"
            + _rows([("Invoice No.", invoice_number), ("Late fee (+ GST)", f"Rs. {late_fee:,.2f}")],
                    ("NOW PAYABLE", f"Rs. {total_payable:,.2f}"), "#c53030")
            + "<p>Please pay the amount above and contact Indram. The updated invoice is attached.</p>")
    ok = await _send(f"Unpaid Indram invoice {invoice_number} — late fee added — {society_name}", to_email,
                     _wrap("Invoice unpaid — late fee added", society_name, body, "#c53030"),
                     [(f"Indram_Invoice_{invoice_number.replace('/', '-')}_late.pdf", pdf_bytes)])
    if ok:
        logger.info("Invoice late email sent | invoice=%s to=%s", invoice_number, to_email)
    return ok


# ── Password reset email ───────────────────────────────────────────────

def _reset_body(full_name, reset_url, expire_minutes) -> str:
    name = full_name or "there"
    return f"""
    <html><body style="font-family:Arial,sans-serif;color:#2d3748;max-width:600px;margin:auto;">
      <div style="background:#1a3c5e;padding:24px;border-radius:8px 8px 0 0;">
        <h2 style="color:white;margin:0;">🔐 Password Reset Request</h2>
        <p style="color:#a0aec0;margin:4px 0 0;">Indram Admin Portal</p>
      </div>
      <div style="background:#f7fafc;padding:24px;border-radius:0 0 8px 8px;">
        <p>Hi <strong>{name}</strong>,</p>
        <p>Click the button below to reset your password. This link expires in <strong>{expire_minutes} minutes</strong> and can only be used once.</p>
        <p style="text-align:center;margin:28px 0;">
          <a href="{reset_url}" style="background:#4f86f7;color:white;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:bold;display:inline-block;">Reset Password</a>
        </p>
        <p style="color:#718096;font-size:13px;">If you didn't request this, ignore this email.</p>
        <p style="color:#a0aec0;font-size:12px;word-break:break-all;">Or copy: {reset_url}</p>
      </div>
    </body></html>
    """


async def send_password_reset_email(to_email: str, full_name: str | None, reset_url: str, expire_minutes: int) -> bool:
    msg = MIMEMultipart("mixed")
    msg["Subject"] = "Reset your Indram admin password"
    msg["From"]    = settings.GMAIL_USER
    msg["To"]      = to_email
    msg.attach(MIMEText(_reset_body(full_name, reset_url, expire_minutes), "html"))
    success = _smtp_send(msg, to_email)
    if success:
        logger.info("Password reset email sent | to=%s", to_email)
    return success