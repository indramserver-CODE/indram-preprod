from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field


class SocietyCreate(BaseModel):
    name:        str
    address:     str | None = None
    indram_rate: Decimal | None = Field(
                     default=None,
                     description="INDRAM platform charge per kWh. Leave blank to use the default ₹1.50.",
                     ge=0,
                 )
    gstin:       str | None = Field(default=None, max_length=15)

    # Late fee — % of that bill, applied once grace days have passed after the due date
    resident_late_fee_pct:        Decimal = Field(default=Decimal("5"), ge=0, le=100)
    resident_late_fee_grace_days: int     = Field(default=0, ge=0)
    indram_late_fee_pct:          Decimal = Field(default=Decimal("5"), ge=0, le=100)
    indram_late_fee_grace_days:   int     = Field(default=0, ge=0)


class SocietyUpdate(BaseModel):
    name:        str | None = None
    address:     str | None = None
    indram_rate: Decimal | None = Field(
                     default=None,
                     description="INDRAM platform charge per kWh. Leave blank to use the default ₹1.50.",
                     ge=0,
                 )
    gstin:       str | None = Field(default=None, max_length=15)

    resident_late_fee_pct:        Decimal | None = Field(default=None, ge=0, le=100)
    resident_late_fee_grace_days: int | None     = Field(default=None, ge=0)
    indram_late_fee_pct:          Decimal | None = Field(default=None, ge=0, le=100)
    indram_late_fee_grace_days:   int | None     = Field(default=None, ge=0)


class SocietyOut(BaseModel):
    id:          int
    name:        str
    address:     str | None
    indram_rate: Decimal | None    # None means fallback ₹1.50 will be used at billing time
    gstin:       str | None

    resident_late_fee_pct:        Decimal
    resident_late_fee_grace_days: int
    indram_late_fee_pct:          Decimal
    indram_late_fee_grace_days:   int

    created_at:  datetime

    model_config = {"from_attributes": True}
