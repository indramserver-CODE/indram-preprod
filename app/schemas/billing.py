from datetime import datetime, date
from decimal import Decimal
from pydantic import BaseModel


class FlatBillOut(BaseModel):
    id:                           int
    flat_id:                      int
    flat_number:                  str | None = None
    owner_name:                   str | None = None
    email:                        str | None = None
    units_consumed:               Decimal
    bill_excl_taxes:              Decimal
    mseb_taxes:                   Decimal
    electricity_charges_incl_tax: Decimal
    indram_charges:               Decimal
    total_payable:                Decimal
    pdf_s3_key:                   str | None
    email_status:                 str
    email_sent_at:                datetime | None
    created_at:                   datetime

    model_config = {"from_attributes": True}


class MonthlyBillOut(BaseModel):
    id:                   int
    meter_id:             int
    meter_number:         str | None = None   # populated by router
    meter_label:          str | None = None   # populated by router
    billing_month:        date
    tariff:               Decimal
    total_bill_amount:    Decimal
    total_units_consumed: Decimal
    effective_unit_rate:  Decimal
    due_date:             date
    created_at:           datetime
    flat_bills:           list[FlatBillOut] = []

    model_config = {"from_attributes": True}


class MonthlyBillSummaryOut(BaseModel):
    id:                   int
    meter_id:             int
    meter_number:         str | None = None   # populated by router
    meter_label:          str | None = None   # populated by router
    billing_month:        date
    total_bill_amount:    Decimal
    total_units_consumed: Decimal
    effective_unit_rate:  Decimal
    due_date:             date
    created_at:           datetime
    total_flats:          int
    emails_sent:          int
    emails_failed:        int
    emails_pending:       int

    model_config = {"from_attributes": True}