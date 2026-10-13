"""
app/routers/rfid.py
-------------------
Super admin  → mounted at /api/rfid
Society admin → mounted at /api/sa/rfid

Super admin:
  GET    /api/rfid/{society_id}                    — list all RFID cards in a society
  POST   /api/rfid/{society_id}/csv                — bulk upload via CSV
  DELETE /api/rfid/{rfid_id}                       — delete a card from DB
  GET    /api/rfid/flat/{flat_id}/pending          — check for in-flight commands
  POST   /api/rfid/flat/{flat_id}/handshake        — on-demand charger online check
  POST   /api/rfid/flat/{flat_id}/deactivate       — DEACTIVATE charger
  POST   /api/rfid/flat/{flat_id}/activate         — ACTIVE charger
  POST   /api/rfid/flat/{flat_id}/add-card         — ADDUID to charger

Society admin (read-only):
  GET    /api/sa/rfid                              — list all cards grouped by flat

New HTTP status codes used:
  200  — success (deactivate / activate confirmed)
  201  — card created and confirmed (add-card)
  400  — validation error (duplicate uid, max cards etc.)
  404  — flat / charger / card not found
  425  — charger offline (handshake timed out) — "Too Early"
          used when operation cannot proceed because charger is offline
          DEACTIVATE/ACTIVE: front-end should offer to queue
          ADDUID: front-end must block — never queue ADDUID
  502  — charger rejected command (ack ok=false with reason)
  504  — charger went offline AFTER handshake succeeded (ack timed out mid-command)
          DEACTIVATE/ACTIVE: command was queued in HiveMQ, will apply on reconnect
          ADDUID: card deleted, operation failed cleanly

Status code decision tree:
  admin clicks → handshake → timeout → 425 (charger offline)
                           → success → send command → ack ok=true → 200/201
                                                   → ack ok=false → 502
                                                   → ack timeout  → 504
"""

import csv
import io
import asyncio
import uuid

from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.rfid import RFIDCard
from app.models.flat import Flat
from app.models.charger import Charger
from app.models.meter import Meter
from app.models.society import Society
from app.models.user import SocietyAdmin, User
from app.schemas.rfid import RFIDOut
from app.dependencies.auth import require_super_admin, require_society_admin

super_router   = APIRouter()
society_router = APIRouter()

REQUIRED_COLUMNS = {"flat_number", "uid"}

HANDSHAKE_TIMEOUT = 10     # seconds — per spec recommendation
ACK_TIMEOUT       = 30     # seconds for DEACTIVATE / ACTIVE / ADDUID ack
DELUID_TIMEOUT    = 15     # seconds for DELUID uid_ack
POLL_INTERVAL     = 1.0


# ── Shared helpers ─────────────────────────────────────────────────────

async def _get_society_or_404(society_id: int, db: AsyncSession) -> Society:
    result = await db.execute(select(Society).where(Society.id == society_id))
    society = result.scalar_one_or_none()
    if not society:
        raise HTTPException(status_code=404, detail="Society not found")
    return society


async def _get_admin_society_id(user: User, db: AsyncSession) -> int:
    result = await db.execute(
        select(SocietyAdmin.society_id).where(SocietyAdmin.user_id == user.id)
    )
    society_id = result.scalar_one_or_none()
    if not society_id:
        raise HTTPException(status_code=403, detail="No society assigned to this admin")
    return society_id


async def _get_charger_for_flat(flat_id: int, db: AsyncSession) -> Charger | None:
    result = await db.execute(select(Charger).where(Charger.flat_id == flat_id))
    return result.scalar_one_or_none()


async def _insert_pending(db, charger_id: str, cmd: str,
                          flat_id: int | None = None,
                          rfid_uid: str | None = None,
                          rfid_card_id: int | None = None) -> int:
    from app.models.command_log import PendingCommand
    now     = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=ACK_TIMEOUT)
    pending = PendingCommand(
        charger_id=charger_id,
        cmd=cmd,
        flat_id=flat_id,
        rfid_uid=rfid_uid,
        rfid_card_id=rfid_card_id,
        status="pending",
        expires_at=expires,
    )
    db.add(pending)
    await db.flush()
    return pending.id


async def _poll_pending(db, pending_id: int, timeout: int = ACK_TIMEOUT) -> dict:
    from app.models.command_log import PendingCommand
    deadline = datetime.now(timezone.utc).timestamp() + timeout
    while True:
        await asyncio.sleep(POLL_INTERVAL)
        result = await db.execute(
            select(PendingCommand).where(PendingCommand.id == pending_id)
            .execution_options(populate_existing=True)
        )
        row = result.scalar_one_or_none()
        if not row:
            return {"status": "failed", "reason": "pending row missing"}
        if row.status != "pending":
            return {"status": row.status, "reason": row.reason}
        if datetime.now(timezone.utc).timestamp() > deadline:
            row.status = "timeout"
            await db.flush()
            return {"status": "timeout", "reason": None}


async def _do_handshake(charger_id: str, society_id: int,
                        meter_id: int, db: AsyncSession) -> dict:
    """
    Send a HANDSHAKE command and wait up to HANDSHAKE_TIMEOUT seconds for ack.
    Returns:
      { "online": True,  "payload": {...} }  — charger responded
      { "online": False, "payload": None  }  — timed out
    """
    from app.mqtt_commands import send_handshake
    from app.ack_waiters import (
        register_handshake, cleanup_handshake, get_handshake_result
    )

    request_id = f"hs-{uuid.uuid4().hex[:16]}"
    event = register_handshake(request_id)

    try:
        await send_handshake(charger_id, society_id, meter_id, request_id)
        try:
            await asyncio.wait_for(event.wait(), timeout=HANDSHAKE_TIMEOUT)
            payload = get_handshake_result(request_id)
            online  = bool(payload and payload.get("online") is True)
            return {"online": online, "payload": payload}
        except asyncio.TimeoutError:
            return {"online": False, "payload": None}
    finally:
        cleanup_handshake(request_id)


async def _get_flat_or_404(flat_id: int, db: AsyncSession) -> Flat:
    """Get flat by id — no society restriction (super admin use)."""
    result = await db.execute(select(Flat).where(Flat.id == flat_id))
    flat = result.scalar_one_or_none()
    if not flat:
        raise HTTPException(status_code=404, detail="Flat not found")
    return flat


# ══ SUPER ADMIN ROUTES ════════════════════════════════════════════════

@super_router.get("/{society_id}", response_model=list[RFIDOut])
async def list_rfid_cards(
    society_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    await _get_society_or_404(society_id, db)
    result = await db.execute(
        select(RFIDCard)
        .join(Flat, RFIDCard.flat_id == Flat.id)
        .where(Flat.society_id == society_id)
        .order_by(Flat.flat_number, RFIDCard.uid)
    )
    return result.scalars().all()


@super_router.post("/{society_id}/csv", status_code=status.HTTP_200_OK)
async def upload_rfid_csv(
    society_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    """
    Bulk upload RFID cards via CSV.
    Required columns: flat_number, uid
    Optional columns: label, uid2, label2
    Max 3 cards per flat. uid2 registers a second card in the same row.
    """
    await _get_society_or_404(society_id, db)

    content = await file.read()
    reader  = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))

    if not REQUIRED_COLUMNS.issubset(set(reader.fieldnames or [])):
        raise HTTPException(
            status_code=400,
            detail=f"CSV must contain columns: {sorted(REQUIRED_COLUMNS)}. Optional: label, uid2, label2",
        )

    flats_result = await db.execute(
        select(Flat.flat_number, Flat.id).where(Flat.society_id == society_id)
    )
    flat_map = {row.flat_number: row.id for row in flats_result}

    existing_result = await db.execute(select(RFIDCard.uid))
    existing_uids: set[str] = set(existing_result.scalars().all())

    count_result = await db.execute(
        select(RFIDCard.flat_id, func.count(RFIDCard.id).label("cnt"))
        .join(Flat, RFIDCard.flat_id == Flat.id)
        .where(Flat.society_id == society_id)
        .group_by(RFIDCard.flat_id)
    )
    rfid_count: dict[int, int] = {row.flat_id: row.cnt for row in count_result}

    imported: list[str] = []
    skipped:  list[dict] = []
    MAX_PER_FLAT = 3

    for i, row in enumerate(reader, start=2):
        flat_number = (row.get("flat_number") or "").strip()
        uid1        = (row.get("uid")   or "").strip().upper()
        label1      = (row.get("label") or "").strip() or None
        uid2        = (row.get("uid2")  or "").strip().upper() or None
        label2      = (row.get("label2") or "").strip() or None

        if not flat_number:
            skipped.append({"row": i, "reason": "flat_number is required"})
            continue
        if flat_number not in flat_map:
            skipped.append({"row": i, "flat_number": flat_number, "reason": "flat not found"})
            continue
        if not uid1:
            skipped.append({"row": i, "flat_number": flat_number, "reason": "uid is required"})
            continue

        flat_id = flat_map[flat_number]

        for uid, label in [(uid1, label1), (uid2, label2)]:
            if not uid:
                continue
            if uid in existing_uids:
                skipped.append({"row": i, "uid": uid, "reason": "duplicate uid"})
            elif rfid_count.get(flat_id, 0) >= MAX_PER_FLAT:
                skipped.append({"row": i, "uid": uid, "reason": f"flat '{flat_number}' already has {MAX_PER_FLAT} cards"})
            else:
                db.add(RFIDCard(flat_id=flat_id, uid=uid, label=label, is_active=True))
                existing_uids.add(uid)
                rfid_count[flat_id] = rfid_count.get(flat_id, 0) + 1
                imported.append(uid)

    await db.flush()
    return {"imported": len(imported), "skipped": len(skipped), "skipped_details": skipped}


@super_router.delete("/{rfid_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rfid(
    rfid_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    """
    Remove an RFID card: charger first (DELUID), then the database.

    1. Handshake (10s) — never queued
       → 425 if charger offline, nothing changed
    2. Save pending DELUID (no FK to the card — it is deleted later)
    3. Send DELUID, wait up to 15s for uid_ack
       → uid_removed / uid_remove_failed(not_found): subscriber deletes the card → 204
       → other uid_remove_failed / cmd_ack rejected: card kept → 502
       → no reply: card kept → 504
    """
    from app.mqtt_commands import send_del_uid

    result = await db.execute(select(RFIDCard).where(RFIDCard.id == rfid_id))
    card   = result.scalar_one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="RFID card not found")

    uid     = card.uid
    charger = await _get_charger_for_flat(card.flat_id, db)
    if not charger:
        # Nothing can be on a charger that does not exist for this flat
        await db.delete(card)
        return

    meter = await db.get(Meter, charger.meter_id)
    if not meter:
        raise HTTPException(status_code=500, detail="Charger has no meter assigned")

    hs = await _do_handshake(charger.charger_id, meter.society_id, charger.meter_id, db)
    if not hs["online"]:
        raise HTTPException(
            status_code=425,
            detail={
                "code":      "CHARGER_OFFLINE",
                "message":   "Charger not responding.",
                "hint":      "RFID cards can only be removed while the charger is online. Please try again later.",
                "can_queue": False,
            },
        )

    pending_id = await _insert_pending(db, charger.charger_id, "DELUID", rfid_uid=uid)
    await db.commit()

    await send_del_uid(charger.charger_id, meter.society_id, charger.meter_id, uid)

    res = await _poll_pending(db, pending_id, timeout=DELUID_TIMEOUT)

    if res["status"] == "timeout":
        raise HTTPException(
            status_code=504,
            detail={
                "code":    "ACK_TIMEOUT",
                "message": "Charger didn't confirm, try again.",
                "hint":    "The card was not removed.",
                "queued":  False,
            },
        )

    if res["status"] == "failed":
        reason = res.get("reason") or "unknown"
        message = ("Failed: rejected by charger" if reason == "rejected_by_charger"
                   else f"Failed: {reason}")
        raise HTTPException(
            status_code=502,
            detail={"code": "CHARGER_REJECTED", "message": message, "reason": reason, "queued": False},
        )

    # done — subscriber already deleted the card


@super_router.get("/flat/{flat_id}/pending")
async def get_flat_pending_command(
    flat_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    from app.models.command_log import PendingCommand
    await _get_flat_or_404(flat_id, db)

    result = await db.execute(
        select(PendingCommand)
        .where(
            PendingCommand.flat_id == flat_id,
            PendingCommand.status.in_(["pending", "timeout"]),
        )
        .order_by(PendingCommand.created_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()

    if not row:
        return {"has_pending": False, "cmd": None, "status": None, "created_at": None}
    return {
        "has_pending": True,
        "cmd":         row.cmd,
        "status":      row.status,
        "created_at":  row.created_at.isoformat() if row.created_at else None,
    }


@super_router.post("/flat/{flat_id}/handshake")
async def handshake_charger(
    flat_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    """
    On-demand charger online check via MQTT handshake.
    Returns charger status, temperature and fw_version if online.
    Returns online=false with timed_out=true if no response in 10s.
    """
    flat = await _get_flat_or_404(flat_id, db)

    charger = await _get_charger_for_flat(flat_id, db)
    if not charger:
        raise HTTPException(status_code=404, detail="No charger assigned to this flat")

    meter = await db.get(Meter, charger.meter_id)
    if not meter:
        raise HTTPException(status_code=500, detail="Charger has no meter assigned")

    result = await _do_handshake(charger.charger_id, meter.society_id, charger.meter_id, db)
    payload = result.get("payload") or {}

    return {
        "charger_id":    charger.charger_id,
        "online":        result["online"],
        "timed_out":     not result["online"],
        "temperature_c": payload.get("temperature_c"),
        "fw_version":    payload.get("fw_version"),
        "status":        payload.get("status"),
        "charger_time":  payload.get("datetime"),
    }


@super_router.post("/flat/{flat_id}/deactivate", status_code=status.HTTP_200_OK)
async def deactivate_flat_rfid(
    flat_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    """
    Deactivate charger for a flat.

    Flow:
    1. Handshake (10s) — confirm charger is online
       → 425 if offline (frontend should offer to queue)
    2. Send DEACTIVATE
    3. Wait for cmd_ack (30s)
       → 200 on ok=true
       → 502 on ok=false (charger rejected — reason in detail)
       → 504 on timeout (charger went offline after handshake — command queued in HiveMQ)
    """
    from app.mqtt_commands import send_deactivate

    flat = await _get_flat_or_404(flat_id, db)

    charger = await _get_charger_for_flat(flat_id, db)
    if not charger:
        raise HTTPException(status_code=404, detail="No charger assigned to this flat")

    meter = await db.get(Meter, charger.meter_id)
    if not meter:
        raise HTTPException(status_code=500, detail="Charger has no meter assigned")

    cards_result = await db.execute(select(RFIDCard).where(RFIDCard.flat_id == flat_id))
    cards = cards_result.scalars().all()
    if not cards:
        raise HTTPException(status_code=404, detail="No RFID cards found for this flat")

    # ── Step 1: Handshake ────────────────────────────────────────────
    hs = await _do_handshake(charger.charger_id, meter.society_id, charger.meter_id, db)
    if not hs["online"]:
        raise HTTPException(
            status_code=425,
            detail={
                "code":    "CHARGER_OFFLINE",
                "message": f"Charger {charger.charger_id} is not responding.",
                "hint":    "The command can be queued — charger will deactivate when it reconnects.",
                "can_queue": True,
            },
        )

    # ── Step 2: Send DEACTIVATE and wait for ack ─────────────────────
    pending_id = await _insert_pending(db, charger.charger_id, "DEACTIVATE", flat_id=flat_id)
    await db.commit()

    await send_deactivate(charger.charger_id, meter.society_id, charger.meter_id)

    result = await _poll_pending(db, pending_id)

    if result["status"] == "timeout":
        raise HTTPException(
            status_code=504,
            detail={
                "code":    "ACK_TIMEOUT",
                "message": f"Charger {charger.charger_id} went offline during the operation.",
                "hint":    "The command was queued. Charger will deactivate when it reconnects.",
                "queued":  True,
            },
        )
    if result["status"] == "failed":
        raise HTTPException(
            status_code=502,
            detail={
                "code":    "CHARGER_REJECTED",
                "message": f"Charger rejected the command.",
                "reason":  result.get("reason", "unknown"),
                "queued":  False,
            },
        )

    return {
        "detail":            f"DEACTIVATE confirmed by charger {charger.charger_id}",
        "charger_id":        charger.charger_id,
        "cards_deactivated": len(cards),
        "status":            "deactivated",
    }


@super_router.post("/flat/{flat_id}/activate", status_code=status.HTTP_200_OK)
async def activate_flat_rfid(
    flat_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    """
    Activate charger for a flat.

    Flow:
    1. Handshake (10s) — confirm charger is online
       → 425 if offline (frontend should offer to queue)
    2. Send ACTIVE
    3. Wait for cmd_ack (30s)
       → 200 on ok=true
       → 502 on ok=false
       → 504 on timeout (command queued in HiveMQ)
    """
    from app.mqtt_commands import send_active

    flat = await _get_flat_or_404(flat_id, db)

    charger = await _get_charger_for_flat(flat_id, db)
    if not charger:
        raise HTTPException(status_code=404, detail="No charger assigned to this flat")

    meter = await db.get(Meter, charger.meter_id)
    if not meter:
        raise HTTPException(status_code=500, detail="Charger has no meter assigned")

    cards_result = await db.execute(select(RFIDCard).where(RFIDCard.flat_id == flat_id))
    cards = cards_result.scalars().all()
    if not cards:
        raise HTTPException(status_code=404, detail="No RFID cards found for this flat")

    # ── Step 1: Handshake ────────────────────────────────────────────
    hs = await _do_handshake(charger.charger_id, meter.society_id, charger.meter_id, db)
    if not hs["online"]:
        raise HTTPException(
            status_code=425,
            detail={
                "code":    "CHARGER_OFFLINE",
                "message": f"Charger {charger.charger_id} is not responding.",
                "hint":    "The command can be queued — charger will activate when it reconnects.",
                "can_queue": True,
            },
        )

    # ── Step 2: Send ACTIVE and wait for ack ─────────────────────────
    pending_id = await _insert_pending(db, charger.charger_id, "ACTIVE", flat_id=flat_id)
    await db.commit()

    await send_active(charger.charger_id, meter.society_id, charger.meter_id)

    result = await _poll_pending(db, pending_id)

    if result["status"] == "timeout":
        raise HTTPException(
            status_code=504,
            detail={
                "code":    "ACK_TIMEOUT",
                "message": f"Charger {charger.charger_id} went offline during the operation.",
                "hint":    "The command was queued. Charger will activate when it reconnects.",
                "queued":  True,
            },
        )
    if result["status"] == "failed":
        raise HTTPException(
            status_code=502,
            detail={
                "code":    "CHARGER_REJECTED",
                "message": "Charger rejected the command.",
                "reason":  result.get("reason", "unknown"),
                "queued":  False,
            },
        )

    return {
        "detail":          f"ACTIVE confirmed by charger {charger.charger_id}",
        "charger_id":      charger.charger_id,
        "cards_activated": len(cards),
        "status":          "activated",
    }


class AddRFIDBody(BaseModel):
    uid:   str
    label: str | None = None


@super_router.post("/flat/{flat_id}/add-card",
                   response_model=RFIDOut,
                   status_code=status.HTTP_201_CREATED)
async def add_rfid_card(
    flat_id: int,
    body: AddRFIDBody,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    """
    Add a new RFID card to a flat charger.

    Flow:
    1. Validate (max 3 cards, unique UID)
    2. Handshake (10s) — ADDUID is never queued — charger MUST be online
       → 425 if offline (frontend must block, not offer queue)
    3. Insert card as is_active=False
    4. Send ADDUID, wait for uid_ack (30s)
       → 201 on uid_added
       → 502 on uid_add_failed (slots_full, duplicate etc.)
       → 504 on timeout → card deleted from DB, clean failure
    """
    from app.ack_waiters import make_key, register, cleanup, get_result
    from app.mqtt_commands import send_add_uid

    flat = await _get_flat_or_404(flat_id, db)

    # Validate max 3 cards
    count_result = await db.execute(
        select(func.count(RFIDCard.id)).where(RFIDCard.flat_id == flat_id)
    )
    if count_result.scalar() >= 3:
        raise HTTPException(status_code=400, detail="This flat already has 3 RFID cards (maximum)")

    # Validate unique UID
    uid = body.uid.strip().upper()
    existing = await db.execute(select(RFIDCard).where(RFIDCard.uid == uid))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"RFID UID {uid} already exists")

    charger = await _get_charger_for_flat(flat_id, db)
    if not charger:
        raise HTTPException(status_code=404, detail="No charger assigned to this flat")

    meter = await db.get(Meter, charger.meter_id)
    if not meter:
        raise HTTPException(status_code=500, detail="Charger has no meter assigned")

    # ── Step 1: Handshake — MUST be online, never queue ADDUID ───────
    hs = await _do_handshake(charger.charger_id, meter.society_id, charger.meter_id, db)
    if not hs["online"]:
        raise HTTPException(
            status_code=425,
            detail={
                "code":      "CHARGER_OFFLINE",
                "message":   f"Charger {charger.charger_id} is not responding.",
                "hint":      "RFID cards can only be added while the charger is online. Please try again later.",
                "can_queue": False,
            },
        )

    # ── Step 2: Insert card as inactive, send ADDUID ──────────────────
    card = RFIDCard(flat_id=flat_id, uid=uid, label=body.label or None, is_active=False)
    db.add(card)
    await db.flush()
    await db.refresh(card)
    card_id = card.id

    pending_id = await _insert_pending(
        db, charger.charger_id, "ADDUID",
        flat_id=flat_id, rfid_uid=uid, rfid_card_id=card_id,
    )
    await db.commit()

    await send_add_uid(charger.charger_id, meter.society_id, charger.meter_id, uid)

    result = await _poll_pending(db, pending_id)

    if result["status"] == "timeout":
        dead_card = await db.get(RFIDCard, card_id)
        if dead_card and not dead_card.is_active:
            await db.delete(dead_card)
            await db.commit()
        raise HTTPException(
            status_code=504,
            detail={
                "code":    "ACK_TIMEOUT",
                "message": f"Charger {charger.charger_id} went offline before confirming the card.",
                "hint":    "The card was not saved. Please try again when the charger is back online.",
                "queued":  False,
            },
        )

    if result["status"] == "failed":
        reason = result.get("reason", "unknown")
        raise HTTPException(
            status_code=502,
            detail={
                "code":    "CHARGER_REJECTED",
                "message": "Charger rejected the card.",
                "reason":  reason,
                "hint":    {
                    "slots_full": "This charger already has 3 cards. Remove one first.",
                    "duplicate_uid": "This UID is already registered on the charger.",
                }.get(reason, f"Charger responded with: {reason}"),
                "queued":  False,
            },
        )

    # Success — subscriber set is_active=True
    await db.refresh(card)
    return RFIDOut(
        id=card.id, flat_id=card.flat_id, flat_number=flat.flat_number,
        uid=card.uid, label=card.label, is_active=card.is_active,
        created_at=card.created_at,
    )


# ══ SOCIETY ADMIN ROUTES (read-only) ══════════════════════════════════

@society_router.get("", response_model=list[RFIDOut])
async def list_my_society_rfid(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_society_admin),
):
    society_id = await _get_admin_society_id(current_user, db)
    result = await db.execute(
        select(
            RFIDCard.id, RFIDCard.flat_id, RFIDCard.uid,
            RFIDCard.label, RFIDCard.is_active, RFIDCard.created_at,
            Flat.flat_number,
        )
        .join(Flat, RFIDCard.flat_id == Flat.id)
        .where(Flat.society_id == society_id)
        .order_by(Flat.flat_number, RFIDCard.uid)
    )
    rows = result.all()
    return [
        RFIDOut(
            id=r.id, flat_id=r.flat_id, flat_number=r.flat_number,
            uid=r.uid, label=r.label, is_active=r.is_active,
            created_at=r.created_at,
        )
        for r in rows
    ]