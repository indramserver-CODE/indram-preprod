from datetime import datetime, date
from decimal import Decimal
from pydantic import BaseModel


class MeterBreakdownItem(BaseModel):
    """Per-meter breakdown shown inside an IndramBill detail view."""
    meter_id:      int
    meter_number:  str
    meter_label:   str
    units_billed:  Decimal
    indram_amount: Decimal

    model_config = {"from_attributes": True}


class IndramBillOut(BaseModel):
    id:                  int
    society_id:          int
    society_name:        str | None = None
    billing_month:       date
    total_indram_amount: Decimal
    total_units:         Decimal
    due_date:            date
    payment_status:      str        # unpaid | paid
    paid_at:             datetime | None
    pdf_s3_key:          str | None
    email_status:        str
    email_sent_at:       datetime | None
    created_at:          datetime
    updated_at:          datetime
    meter_breakdown:     list[MeterBreakdownItem] = []

    model_config = {"from_attributes": True}


class IndramBillSummaryOut(BaseModel):
    id:                  int
    society_id:          int
    society_name:        str | None = None
    billing_month:       date
    total_indram_amount: Decimal
    total_units:         Decimal
    due_date:            date
    payment_status:      str
    paid_at:             datetime | None
    email_status:        str
    created_at:          datetime
    updated_at:          datetime

    model_config = {"from_attributes": True}