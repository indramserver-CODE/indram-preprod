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


class SocietyUpdate(BaseModel):
    name:        str | None = None
    address:     str | None = None
    indram_rate: Decimal | None = Field(
                     default=None,
                     description="INDRAM platform charge per kWh. Leave blank to use the default ₹1.50.",
                     ge=0,
                 )


class SocietyOut(BaseModel):
    id:          int
    name:        str
    address:     str | None
    indram_rate: Decimal | None    # None means fallback ₹1.50 will be used at billing time
    created_at:  datetime

    model_config = {"from_attributes": True}