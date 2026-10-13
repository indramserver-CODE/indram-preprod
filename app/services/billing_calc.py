"""
app/services/billing_calc.py
----------------------------
Pure billing rules and arithmetic — no DB, no I/O, unit-tested in tests/test_billing_calc.py.

Resident bill (per flat):
  effective_rate         = MSEB bill amount ÷ MSEB bill units
  bill_excl_taxes        = u × tariff
  electricity_incl_tax   = u × effective_rate
  mseb_taxes             = electricity_incl_tax − bill_excl_taxes
  indram_charges         = u × indram_rate                       (before GST)
  cgst = sgst            = 9% of indram_charges
  indram_total           = indram_charges + cgst + sgst
  total_payable          = electricity_incl_tax + indram_total
  late_fee (if unpaid)   = late_fee_pct% of total_payable          (no GST)

Indram invoice (per send):
  late_fee (if flagged)  = late_fee_pct% of charges
  cgst = sgst            = 9% of (charges + late_fee)
  total_payable          = charges + late_fee + cgst + sgst

Billing period: sessions count by the date they ended, 00:00 on From to 23:59
on Till, Indian time. Periods follow each other with no gap or overlap, and a
period can be generated only 3 days after its Till date.
"""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta

IST                   = ZoneInfo("Asia/Kolkata")
DEFAULT_INDRAM_RATE   = Decimal("1.50")
GST_HALF_RATE         = Decimal("0.09")     # CGST 9% + SGST 9% = 18%
GENERATE_AFTER_DAYS   = 3                   # late charging records arrive within this window


def round2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def round4(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def today_ist() -> date:
    return datetime.now(IST).date()


# ── Billing period ────────────────────────────────────────────────────

def period_bounds_utc(period_from: date, period_till: date) -> tuple[datetime, datetime]:
    """[start, end) in UTC for sessions ended between 00:00 From and 23:59:59 Till, Indian time."""
    start = datetime.combine(period_from, time.min, IST)
    end   = datetime.combine(period_till + timedelta(days=1), time.min, IST)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def earliest_generate_date(period_till: date) -> date:
    return period_till + timedelta(days=GENERATE_AFTER_DAYS)


def suggest_next_period(last_till: date | None) -> tuple[date | None, date | None]:
    """From = day after the last Till; Till = one month later (the admin can change it)."""
    if last_till is None:
        return None, None
    period_from = last_till + timedelta(days=1)
    return period_from, period_from + relativedelta(months=1) - timedelta(days=1)


def validate_period(period_from: date, period_till: date, last_till: date | None,
                    today: date) -> str | None:
    """Return an error message, or None if the period can be generated today."""
    if period_till < period_from:
        return "Till date must be on or after the From date."
    if last_till is not None and period_from != last_till + timedelta(days=1):
        expected = last_till + timedelta(days=1)
        return (f"Billing periods must follow each other with no gap or overlap. "
                f"The last bill ended on {last_till:%d %b %Y}, so this one must start on {expected:%d %b %Y}.")
    earliest = earliest_generate_date(period_till)
    if today < earliest:
        return (f"Bills for a period ending {period_till:%d %b %Y} can be generated from "
                f"{earliest:%d %b %Y}, so late charging records are included.")
    return None


def billing_month_for(period_till: date) -> date:
    """Month a period is reported under — the month its Till date falls in."""
    return period_till.replace(day=1)


# ── Resident bill ─────────────────────────────────────────────────────

def effective_rate(mseb_amount: Decimal, mseb_units: Decimal) -> Decimal:
    if mseb_units <= 0:
        raise ValueError("MSEB units must be greater than zero.")
    return round4(mseb_amount / mseb_units)


def gst_split(amount: Decimal) -> tuple[Decimal, Decimal]:
    """CGST 9% and SGST 9% of an amount, each rounded to paise."""
    half = round2(amount * GST_HALF_RATE)
    return half, half


def calculate_flat_bill(units: Decimal, tariff: Decimal, eff_rate: Decimal,
                        indram_rate: Decimal) -> dict:
    u = round4(units)
    bill_excl_taxes      = round2(u * tariff)
    electricity_incl_tax = round2(u * eff_rate)
    indram_charges       = round2(u * indram_rate)
    cgst, sgst           = gst_split(indram_charges)
    indram_total         = indram_charges + cgst + sgst
    return {
        "units_consumed":               u,
        "bill_excl_taxes":              bill_excl_taxes,
        "mseb_taxes":                   electricity_incl_tax - bill_excl_taxes,
        "electricity_charges_incl_tax": electricity_incl_tax,
        "indram_rate":                  indram_rate,
        "indram_charges":               indram_charges,
        "indram_cgst":                  cgst,
        "indram_sgst":                  sgst,
        "indram_total":                 indram_total,
        "total_payable":                electricity_incl_tax + indram_total,
    }


# ── Late fee ──────────────────────────────────────────────────────────

def late_fee(amount: Decimal, pct: Decimal) -> Decimal:
    return round2(amount * pct / Decimal(100))


def late_fee_allowed_from(due_date: date, grace_days: int) -> date:
    """First day a bill can be marked unpaid / flagged late: after the due date plus grace days."""
    return due_date + timedelta(days=grace_days + 1)


# ── Indram invoice ────────────────────────────────────────────────────

def calculate_indram_invoice(charges: Decimal, late_fee_pct: Decimal | None = None) -> dict:
    """Pass late_fee_pct only when the super admin has raised the late flag."""
    fee        = late_fee(charges, late_fee_pct) if late_fee_pct is not None else Decimal("0.00")
    cgst, sgst = gst_split(charges + fee)
    return {
        "total_indram_amount": charges,
        "late_fee":            fee,
        "cgst":                cgst,
        "sgst":                sgst,
        "total_payable":       charges + fee + cgst + sgst,
    }


def financial_year(d: date) -> str:
    """Indian financial year, April–March: 14 Oct 2026 → "2026-27"."""
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def format_invoice_number(fy: str, n: int) -> str:
    return f"IND/{fy}/{n:04d}"


def format_bill_number(society_id: int, n: int) -> str:
    return f"SOC{society_id}-{n:06d}"


# ── Amount in words (Indian numbering) ────────────────────────────────

_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
         "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen",
         "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _below_100(n: int) -> str:
    if n < 20:
        return _ONES[n]
    return (_TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else "")).strip()


def _below_1000(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    parts = []
    if hundreds:
        parts.append(f"{_ONES[hundreds]} Hundred")
    if rest:
        parts.append(_below_100(rest))
    return " ".join(parts)


def _int_to_words(n: int) -> str:
    if n == 0:
        return "Zero"
    parts = []
    for size, name in ((10**7, "Crore"), (10**5, "Lakh"), (10**3, "Thousand")):
        if n >= size:
            count, n = divmod(n, size)
            parts.append(f"{_int_to_words(count) if count >= 100 else _below_100(count)} {name}")
    if n:
        parts.append(_below_1000(n))
    return " ".join(parts)


def amount_in_words(amount: Decimal) -> str:
    """₹1,297.50 → "Rupees One Thousand Two Hundred Ninety Seven and Fifty Paise Only"."""
    amount = round2(amount)
    rupees = int(amount)
    paise  = int((amount - rupees) * 100)
    words  = f"Rupees {_int_to_words(rupees)}"
    if paise:
        words += f" and {_below_100(paise)} Paise"
    return words + " Only"
