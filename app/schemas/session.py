from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel


class SessionOut(BaseModel):
    id:             int
    session_id:     int
    charger_id:     str
    rfid_uid:       str | None
    start_kwhr:     Decimal | None
    end_kwhr:       Decimal | None
    units_consumed: Decimal | None
    status:         str
    fault_code:     str | None
    fw_version:     str | None
    started_at:     datetime
    ended_at:       datetime | None

    model_config = {"from_attributes": True}


class OrphanMessageOut(BaseModel):
    id:          int
    charger_id:  str | None
    session_id:  int | None
    event:       str | None
    payload:     str | None
    is_reviewed: bool
    received_at: datetime

    model_config = {"from_attributes": True}