from datetime import datetime
from pydantic import BaseModel, EmailStr


class FlatCreate(BaseModel):
    flat_number: str
    owner_name: str | None = None
    email: EmailStr | None = None


class FlatUpdate(BaseModel):
    flat_number: str | None = None
    owner_name: str | None = None
    email: EmailStr | None = None


class FlatOut(BaseModel):
    id:           int
    society_id:   int
    flat_number:  str
    owner_name:   str | None
    email:        str | None
    charger_id:   str | None = None    # joined from chargers table
    meter_id:     int | None = None    # joined from chargers → meters
    meter_label:  str | None = None    # joined from meters.label
    charger_status: str | None = None  # live status from charger_status table
    fault_code:   str | None = None
    created_at:   datetime

    model_config = {"from_attributes": True}