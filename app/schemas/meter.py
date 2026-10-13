from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel


class MeterCreate(BaseModel):
    meter_number:    str
    label:           str
    sanctioned_load: Decimal | None = None   # kW
    location:        str | None = None


class MeterUpdate(BaseModel):
    meter_number:    str | None = None
    label:           str | None = None
    sanctioned_load: Decimal | None = None
    location:        str | None = None


class MeterOut(BaseModel):
    id:              int
    society_id:      int
    meter_number:    str
    label:           str
    sanctioned_load: Decimal | None
    location:        str | None
    created_at:      datetime

    model_config = {"from_attributes": True}


class MeterSummaryOut(BaseModel):
    """Lightweight meter info returned to society admins (no edit actions)."""
    id:              int
    meter_number:    str
    label:           str
    sanctioned_load: Decimal | None
    location:        str | None
    charger_count:   int = 0   # populated by the router, not from ORM directly

    model_config = {"from_attributes": True}