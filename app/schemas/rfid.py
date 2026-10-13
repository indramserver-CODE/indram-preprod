from datetime import datetime
from pydantic import BaseModel


class RFIDCreate(BaseModel):
    uid: str
    label: str | None = None


class RFIDUpdate(BaseModel):
    label: str | None = None
    is_active: bool | None = None


class RFIDOut(BaseModel):
    id: int
    flat_id: int
    flat_number: str | None = None   # joined from flats table
    uid: str
    label: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}