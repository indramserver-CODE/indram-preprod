"""
app/services/email_service.py
------------------------------
Sends emails via Gmail SMTP.
  - send_bill_email           — flat EV charging bill with PDF
  - send_indram_bill_email    — Indram platform invoice to society admin
  - send_password_reset_email — password reset link
"""

import smtplib
import logging
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


# ── Flat bill email ───────────────────────────────────────────────────

def _flat_bill_body(owner_name, flat_number, society_name, billing_month, total_payable, due_date) -> str:
    month_str = billing_month.strftime("%B %Y")
    name      = owner_name or "Resident"
    return f"""
    <html><body style="font-family:Arial,sans-serif;color:#2d3748;max-width:600px;margin:auto;">
      <div style="background:#1a3c5e;padding:24px;border-radius:8px 8px 0 0;">
        <h2 style="color:white;margin:0;">⚡ EV Charging Bill</h2>
        <p style="color:#a0aec0;margin:4px 0 0;">{society_name}</p>
      </div>
      <div style="background:#f7fafc;padding:24px;border-radius:0 0 8px 8px;">
        <p>Dear <strong>{name}</strong>,</p>
        <p>Your EV charging bill for <strong>{month_str}</strong> has been generated.</p>
        <table style="width:100%;border-collapse:collapse;margin:16px 0;">
          <tr style="background:#e2e8f0;"><td style="padding:10px;font-weight:bold;">Flat Number</td><td style="padding:10px;">{flat_number}</td></tr>
          <tr><td style="padding:10px;font-weight:bold;">Billing Month</td><td style="padding:10px;">{month_str}</td></tr>
          <tr style="background:#e2e8f0;"><td style="padding:10px;font-weight:bold;">Due Date</td><td style="padding:10px;">{due_date.strftime("%d %b %Y")}</td></tr>
          <tr style="background:#c53030;"><td style="padding:12px;font-weight:bold;color:white;">TOTAL AMOUNT PAYABLE</td><td style="padding:12px;font-weight:bold;color:white;font-size:18px;">&#8377; {total_payable:.2f}</td></tr>
        </table>
        <p>Please find your detailed bill attached as a PDF.</p>
        <p style="color:#718096;font-size:13px;">This is an automated email. For queries contact your society admin.</p>
      </div>
    </body></html>
    """


async def send_bill_email(
    to_email: str, owner_name: str | None, flat_number: str, society_name: str,
    billing_month: date, total_payable: Decimal, due_date: date,
    pdf_bytes: bytes, bill_number: str,
) -> bool:
    month_str = billing_month.strftime("%B %Y")
    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"{society_name} — EV Charging Bill for {month_str} | Flat {flat_number}"
    msg["From"]    = settings.GMAIL_USER
    msg["To"]      = to_email
    msg.attach(MIMEText(_flat_bill_body(owner_name, flat_number, society_name,
                                         billing_month, total_payable, due_date), "html"))
    pdf_part = MIMEApplication(pdf_bytes, _subtype="pdf")
    pdf_part.add_header("Content-Disposition", "attachment",
                         filename=f"Bill_{flat_number}_{billing_month.strftime('%Y_%m')}.pdf")
    msg.attach(pdf_part)
    success = _smtp_send(msg, to_email)
    if success:
        logger.info("Flat bill email sent | flat=%s to=%s", flat_number, to_email)
    return success


# ── Indram invoice email ───────────────────────────────────────────────

def _indram_invoice_body(society_name, billing_month, total_indram_amount, due_date, invoice_number) -> str:
    month_str = billing_month.strftime("%B %Y")
    return f"""
    <html><body style="font-family:Arial,sans-serif;color:#2d3748;max-width:600px;margin:auto;">
      <div style="background:#276749;padding:24px;border-radius:8px 8px 0 0;">
        <h2 style="color:white;margin:0;">⚡ INDRAM Platform Invoice</h2>
        <p style="color:#c6f6d5;margin:4px 0 0;">EV Charging Management Platform</p>
      </div>
      <div style="background:#f7fafc;padding:24px;border-radius:0 0 8px 8px;">
        <p>Dear Society Admin,</p>
        <p>The Indram platform service invoice for <strong>{society_name}</strong>
           for <strong>{month_str}</strong> has been generated.</p>
        <table style="width:100%;border-collapse:collapse;margin:16px 0;">
          <tr style="background:#e2e8f0;"><td style="padding:10px;font-weight:bold;">Society</td><td style="padding:10px;">{society_name}</td></tr>
          <tr><td style="padding:10px;font-weight:bold;">Billing Month</td><td style="padding:10px;">{month_str}</td></tr>
          <tr style="background:#e2e8f0;"><td style="padding:10px;font-weight:bold;">Invoice Number</td><td style="padding:10px;">{invoice_number}</td></tr>
          <tr><td style="padding:10px;font-weight:bold;">Due Date</td><td style="padding:10px;">{due_date.strftime("%d %b %Y")}</td></tr>
          <tr style="background:#276749;">
            <td style="padding:12px;font-weight:bold;color:white;">TOTAL AMOUNT PAYABLE TO INDRAM</td>
            <td style="padding:12px;font-weight:bold;color:white;font-size:18px;">&#8377; {total_indram_amount:.2f}</td>
          </tr>
        </table>
        <p>Please find the detailed invoice attached as a PDF. Payment details are included in the invoice.</p>
        <p style="color:#718096;font-size:13px;">
          This is an automated invoice from the Indram platform.
          For queries, contact <a href="mailto:platform@indram.in">platform@indram.in</a>.
        </p>
      </div>
    </body></html>
    """


async def send_indram_bill_email(
    to_email:            str,
    society_name:        str,
    billing_month:       date,
    total_indram_amount: Decimal,
    due_date:            date,
    invoice_number:      str,
    pdf_bytes:           bytes,
) -> bool:
    month_str = billing_month.strftime("%B %Y")
    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"Indram Platform Invoice — {society_name} — {month_str}"
    msg["From"]    = settings.GMAIL_USER
    msg["To"]      = to_email
    msg.attach(MIMEText(_indram_invoice_body(
        society_name, billing_month, total_indram_amount, due_date, invoice_number,
    ), "html"))
    pdf_part = MIMEApplication(pdf_bytes, _subtype="pdf")
    pdf_part.add_header("Content-Disposition", "attachment",
                         filename=f"Indram_Invoice_{billing_month.strftime('%Y_%m')}.pdf")
    msg.attach(pdf_part)
    success = _smtp_send(msg, to_email)
    if success:
        logger.info("Indram invoice email sent | society=%s to=%s", society_name, to_email)
    return success


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