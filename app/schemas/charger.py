from datetime import datetime
from typing import Literal
from pydantic import BaseModel


class ChargerCreate(BaseModel):
    charger_id: str
    meter_id:   int
    flat_id:    int


class ChargerUpdate(BaseModel):
    is_active:       bool | None = None
    connection_type: Literal["hub", "mesh"] | None = None   # mesh node: offline after 12 min silent, else 75


class ChargerOut(BaseModel):
    id:           int
    meter_id:     int
    flat_id:      int
    charger_id:   str
    fw_version:   str | None
    is_active:    bool
    last_seen_at: datetime | None
    created_at:   datetime
    # Live state from charger messages
    status:            str            # charging | available | locked | fault | offline | never_connected
    fault_code:        str | None
    lock_reasons:      list[str]
    connection_type:   str            # hub | mesh
    status_updated_at: datetime | None
    last_reset_reason: str | None
    pending_cmd:  str | None = None    # DEACTIVATE(_ALL) | ACTIVE / ACTIVATE_ALL queued, not yet confirmed
    still_locked: bool = False         # last ACTIVATE_ALL acked 'still_locked' (another lock keeps it off)

    model_config = {"from_attributes": True}