"""
app/routers/chargers.py
-----------------------
Super admin only.

GET    /api/chargers/{society_id}          — list all chargers for a society
POST   /api/chargers/{society_id}/csv      — bulk import chargers via CSV
POST   /api/chargers/{society_id}/deactivate-all — broadcast DEACTIVATE_ALL, queue for offline chargers
POST   /api/chargers/{society_id}/activate-all   — broadcast ACTIVATE_ALL, queue for offline chargers
PUT    /api/chargers/{charger_id}          — update charger (e.g. toggle is_active)
DELETE /api/chargers/{charger_id}          — delete charger

CSV format (required columns): flat_number, charger_id, meter_number
  flat_number   — must match an existing flat in this society
  charger_id    — globally unique charger identifier (e.g. EZC001)
  meter_number  — must match an existing meter in this society
"""

import csv
import io
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.database import get_db
from app.models.charger import Charger
from app.models.command_log import PendingCommand
from app.models.flat import Flat
from app.models.meter import Meter
from app.models.society import Society
from app.schemas.charger import ChargerOut, ChargerUpdate
from app.dependencies.auth import require_super_admin

router = APIRouter()
logger = logging.getLogger(__name__)

BULK_CMDS = ["DEACTIVATE_ALL", "ACTIVATE_ALL"]

REQUIRED_COLUMNS = {"flat_number", "charger_id", "meter_number"}


async def _get_society_or_404(society_id: int, db: AsyncSession) -> Society:
    result = await db.execute(select(Society).where(Society.id == society_id))
    society = result.scalar_one_or_none()
    if not society:
        raise HTTPException(status_code=404, detail="Society not found")
    return society


@router.get("/{society_id}", response_model=list[ChargerOut])
async def list_chargers(
    society_id: int,
    meter_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    """
    List all chargers for a society, optionally filtered by meter_id.
    Joins through Meter so we can scope to a society even though
    Charger now holds meter_id (not society_id directly).
    """
    await _get_society_or_404(society_id, db)

    q = (
        select(Charger)
        .join(Meter, Charger.meter_id == Meter.id)
        .where(Meter.society_id == society_id)
        .order_by(Charger.charger_id)
    )
    if meter_id is not None:
        q = q.where(Charger.meter_id == meter_id)

    chargers = (await db.execute(q)).scalars().all()
    ids = [c.charger_id for c in chargers]

    pending = {}
    latest_done = {}
    if ids:
        # Queued (de)activations the charger hasn't confirmed yet — shown as a "pending" tag
        pend_rows = await db.execute(
            select(PendingCommand.charger_id, PendingCommand.cmd)
            .where(PendingCommand.charger_id.in_(ids),
                   PendingCommand.cmd.in_((*BULK_CMDS, "DEACTIVATE", "ACTIVE")),
                   PendingCommand.status == "pending",
                   PendingCommand.expires_at > datetime.now(timezone.utc))
            .order_by(PendingCommand.created_at)
        )
        pending = {r.charger_id: r.cmd for r in pend_rows}   # newest wins

        done_rows = await db.execute(
            select(PendingCommand.charger_id, PendingCommand.cmd, PendingCommand.reason)
            .where(PendingCommand.charger_id.in_(ids),
                   PendingCommand.cmd.in_(BULK_CMDS),
                   PendingCommand.status == "done")
            .distinct(PendingCommand.charger_id)
            .order_by(PendingCommand.charger_id, PendingCommand.resolved_at.desc())
        )
        latest_done = {r.charger_id: r for r in done_rows}

    out = []
    for c in chargers:
        d = latest_done.get(c.charger_id)
        out.append(ChargerOut.model_validate(c).model_copy(update={
            "pending_cmd":  pending.get(c.charger_id),
            "still_locked": bool(d and d.cmd == "ACTIVATE_ALL" and d.reason == "still_locked" and not c.is_active),
        }))
    return out


async def _queue_society_command(society_id: int, cmd: str, db: AsyncSession) -> dict:
    """
    Queue `cmd` (DEACTIVATE_ALL | ACTIVATE_ALL) for every charger in the society, then broadcast it.
    Chargers that ack are resolved by the MQTT subscriber; the rest stay 'pending' and get the
    per-charger command on their next heartbeat. The opposite command is cancelled.
    """
    from app import mqtt_commands

    await _get_society_or_404(society_id, db)
    ids = (await db.execute(
        select(Charger.charger_id)
        .join(Meter, Charger.meter_id == Meter.id)
        .where(Meter.society_id == society_id)
    )).scalars().all()
    if not ids:
        raise HTTPException(status_code=400, detail="This society has no chargers")

    now = datetime.now(timezone.utc)
    # Supersede anything still queued for these chargers (opposite command, or a repeat click)
    await db.execute(
        update(PendingCommand)
        .where(PendingCommand.charger_id.in_(ids),
               PendingCommand.cmd.in_(BULK_CMDS),
               PendingCommand.status == "pending")
        .values(status="cancelled", resolved_at=now)
    )
    far_future = now + timedelta(days=3650)   # retried until acked or cancelled
    db.add_all([
        PendingCommand(charger_id=cid, cmd=cmd, society_id=society_id,
                       status="pending", expires_at=far_future)
        for cid in ids
    ])
    await db.commit()   # rows must exist before acks start arriving

    sender = mqtt_commands.send_deactivate_all if cmd == "DEACTIVATE_ALL" else mqtt_commands.send_activate_all
    try:
        await sender(society_id)
        sent = True
    except Exception as e:
        logger.error("%s broadcast failed | society=%s error=%s", cmd, society_id, e)
        sent = False   # still queued — each charger is retried when its heartbeat arrives

    return {"command": cmd, "chargers": len(ids), "broadcast_sent": sent}


@router.post("/{society_id}/deactivate-all")
async def deactivate_all_chargers(
    society_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    return await _queue_society_command(society_id, "DEACTIVATE_ALL", db)


@router.post("/{society_id}/activate-all")
async def activate_all_chargers(
    society_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    return await _queue_society_command(society_id, "ACTIVATE_ALL", db)


@router.post("/{society_id}/csv", status_code=status.HTTP_200_OK)
async def upload_chargers_csv(
    society_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    """
    Bulk import chargers from a CSV file.

    Required CSV columns:
      - flat_number  : must match an existing flat in this society
      - charger_id   : globally unique charger device ID
      - meter_number : must match an existing meter in this society

    Rows that fail validation are skipped and reported in skipped_details.
    Successfully imported rows are committed atomically.
    """
    await _get_society_or_404(society_id, db)

    content = await file.read()
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV file must be UTF-8 encoded")

    if not REQUIRED_COLUMNS.issubset(set(reader.fieldnames or [])):
        raise HTTPException(
            status_code=400,
            detail=f"CSV must contain columns: {sorted(REQUIRED_COLUMNS)}",
        )

    # Build flat_number → flat_id lookup for this society
    flats_result = await db.execute(
        select(Flat.flat_number, Flat.id).where(Flat.society_id == society_id)
    )
    flat_map: dict[str, int] = {row.flat_number: row.id for row in flats_result}

    # Build meter_number → meter_id lookup for this society
    meters_result = await db.execute(
        select(Meter.meter_number, Meter.id).where(Meter.society_id == society_id)
    )
    meter_map: dict[str, int] = {row.meter_number: row.id for row in meters_result}

    # Global set of existing charger_ids (charger_id is unique across all societies)
    existing_result = await db.execute(select(Charger.charger_id))
    existing_charger_ids: set[str] = set(existing_result.scalars().all())

    # Set of flat_ids that already have a charger (1:1 enforced at DB level, but pre-check here)
    assigned_result = await db.execute(select(Charger.flat_id))
    assigned_flat_ids: set[int] = set(assigned_result.scalars().all())

    imported: list[str] = []
    skipped:  list[dict] = []

    for i, row in enumerate(reader, start=2):
        flat_number   = (row.get("flat_number")   or "").strip()
        charger_id    = (row.get("charger_id")    or "").strip()
        meter_number  = (row.get("meter_number")  or "").strip()

        # Validate all required fields present
        if not flat_number or not charger_id or not meter_number:
            skipped.append({
                "row": i,
                "reason": "flat_number, charger_id and meter_number are all required",
            })
            continue

        # Validate flat exists in this society
        if flat_number not in flat_map:
            skipped.append({
                "row": i,
                "charger_id": charger_id,
                "reason": f"flat '{flat_number}' not found in society",
            })
            continue

        # Validate meter exists in this society
        if meter_number not in meter_map:
            skipped.append({
                "row": i,
                "charger_id": charger_id,
                "reason": f"meter '{meter_number}' not found in society",
            })
            continue

        flat_id  = flat_map[flat_number]
        meter_id = meter_map[meter_number]

        # Flat already has a charger
        if flat_id in assigned_flat_ids:
            skipped.append({
                "row": i,
                "charger_id": charger_id,
                "reason": f"flat '{flat_number}' already has a charger assigned",
            })
            continue

        # Duplicate charger_id
        if charger_id in existing_charger_ids:
            skipped.append({
                "row": i,
                "charger_id": charger_id,
                "reason": "charger_id already exists",
            })
            continue

        charger = Charger(
            meter_id=meter_id,
            flat_id=flat_id,
            charger_id=charger_id,
        )
        db.add(charger)

        # Track in-memory to catch duplicates within the same CSV
        existing_charger_ids.add(charger_id)
        assigned_flat_ids.add(flat_id)
        imported.append(charger_id)

    await db.flush()
    await db.commit()

    return {
        "imported":        len(imported),
        "skipped":         len(skipped),
        "skipped_details": skipped,
    }


@router.put("/{charger_id}", response_model=ChargerOut)
async def update_charger(
    charger_id: str,
    body: ChargerUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    result = await db.execute(select(Charger).where(Charger.charger_id == charger_id))
    charger = result.scalar_one_or_none()
    if not charger:
        raise HTTPException(status_code=404, detail="Charger not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(charger, field, value)

    await db.flush()
    await db.refresh(charger)
    await db.commit()
    return charger


@router.delete("/{charger_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_charger(
    charger_id: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    result = await db.execute(select(Charger).where(Charger.charger_id == charger_id))
    charger = result.scalar_one_or_none()
    if not charger:
        raise HTTPException(status_code=404, detail="Charger not found")
    await db.delete(charger)
    await db.commit()