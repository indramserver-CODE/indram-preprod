from datetime import datetime, date
from decimal import Decimal
from pydantic import BaseModel


class NextPeriodOut(BaseModel):
    meter_id:               int
    last_till:              date | None   # None before the meter's first bill
    suggested_from:         date | None
    suggested_till:         date | None
    earliest_generate_date: date | None   # for the suggested Till date
    draft_id:               int | None    # an unsent preview already exists


class BillPreviewOut(BaseModel):
    monthly_bill_id:        int
    status:                 str
    period_from:            date
    period_till:            date
    due_date:               date
    effective_rate:         Decimal
    replaces_id:            int | None
    total_flats:            int
    total_units:            Decimal
    total_electricity:      Decimal
    total_indram:           Decimal
    total_amount:           Decimal
    flats_with_adjustments: int
    flats_without_email:    int


class FlatBillOut(BaseModel):
    id:                           int
    flat_id:                      int
    bill_number:                  str | None
    flat_number:                  str
    owner_name:                   str | None
    email:                        str | None
    charger_id:                   str | None
    units_consumed:               Decimal
    adjustment_units:             Decimal
    bill_excl_taxes:              Decimal
    mseb_taxes:                   Decimal
    electricity_charges_incl_tax: Decimal
    indram_charges:               Decimal
    indram_cgst:                  Decimal
    indram_sgst:                  Decimal
    indram_total:                 Decimal
    total_payable:                Decimal
    payment_status:               str
    late_fee:                     Decimal
    marked_unpaid_at:             datetime | None
    paid_at:                      datetime | None
    email_status:                 str
    email_sent_at:                datetime | None
    created_at:                   datetime

    model_config = {"from_attributes": True}


class MonthlyBillSummaryOut(BaseModel):
    id:                   int
    meter_id:             int
    meter_number:         str | None = None
    meter_label:          str | None = None
    period_from:          date
    period_till:          date
    billing_month:        date
    status:               str
    total_bill_amount:    Decimal
    total_units_consumed: Decimal
    effective_unit_rate:  Decimal
    due_date:             date
    sent_at:              datetime | None
    replaces_id:          int | None
    created_at:           datetime
    total_flats:          int
    total_amount:         Decimal
    flats_paid:           int
    flats_unpaid:         int
    emails_sent:          int
    emails_failed:        int
    emails_pending:       int


class MonthlyBillOut(BaseModel):
    id:                   int
    meter_id:             int
    meter_number:         str | None = None
    meter_label:          str | None = None
    period_from:          date
    period_till:          date
    billing_month:        date
    status:               str
    tariff:               Decimal
    total_bill_amount:    Decimal
    total_units_consumed: Decimal
    effective_unit_rate:  Decimal
    due_date:             date
    sent_at:              datetime | None
    cancelled_at:         datetime | None
    replaces_id:          int | None
    created_at:           datetime
    flat_bills:           list[FlatBillOut] = []
