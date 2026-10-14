from datetime import datetime, date
from decimal import Decimal
from pydantic import BaseModel


class IndramBillSummaryOut(BaseModel):
    id:                  int
    invoice_number:      str
    society_id:          int
    society_name:        str | None = None
    meter_id:            int | None = None
    meter_label:         str | None = None
    billing_month:       date
    period_from:         date
    period_till:         date
    total_units:         Decimal
    total_indram_amount: Decimal       # charges before late fee and GST
    late_flag:           bool
    late_fee:            Decimal
    cgst:                Decimal
    sgst:                Decimal
    rounding:            Decimal       # to the nearest rupee
    total_payable:       Decimal
    due_date:            date
    status:              str           # issued | cancelled
    payment_status:      str           # unpaid | paid
    paid_at:             datetime | None
    email_status:        str
    has_receipt:         bool          # paid → "Download receipt"
    created_at:          datetime


class IndramBillOut(IndramBillSummaryOut):
    meter_number:          str | None = None
    indram_rate:           Decimal
    late_fee_pct:          Decimal | None
    society_gstin:         str | None
    monthly_bill_id:       int
    replaces_number:       str | None = None   # this invoice replaced a cancelled one
    replaced_by_number:    str | None = None   # this (cancelled) invoice was replaced
    late_flag_allowed_from: date | None = None # due date + society's Indram grace days
    email_sent_at:         datetime | None
    updated_at:            datetime
