from datetime import datetime
from pydantic import BaseModel


class ChargerCreate(BaseModel):
    charger_id: str
    meter_id:   int
    flat_id:    int


class ChargerUpdate(BaseModel):
    is_active: bool | None = None


class ChargerOut(BaseModel):
    id:           int
    meter_id:     int
    flat_id:      int
    charger_id:   str
    fw_version:   str | None
    is_active:    bool
    last_seen_at: datetime | None
    created_at:   datetime
    pending_cmd:  str | None = None    # DEACTIVATE_ALL | ACTIVATE_ALL queued, not yet confirmed
    still_locked: bool = False         # last ACTIVATE_ALL acked 'still_locked' (another lock keeps it off)

    model_config = {"from_attributes": True}