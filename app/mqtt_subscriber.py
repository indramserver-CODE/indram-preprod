"""
app/mqtt_subscriber.py
----------------------
Inbound MQTT messages — charger to server (firmware v6.4.0).

Topic structure:
  indram/{society_id}/{meter_id}/{charger_id}/{direction}/{event}
  e.g. indram/2/4/EZC001/evt/charging_started

Subscribed wildcards:
  indram/+/+/+/evt/#    QoS 1 — all charger events
  indram/+/+/+/ack/#    QoS 1 — all ack messages

Inbound events (direction = evt):
  charging_started          QoS 1 — billing critical
  session_resumed           QoS 1 — power-cut recovery, updates existing session
  charging_ended            QoS 1 — billing critical
  charging_ended_error      QoS 1 — billing critical
  charging_stopped_by_admin QoS 1 — billing critical
  heartbeat                 QoS 0 — every 60 minutes, keep-alive only
  status                    QoS 0 — every 30s while session active (retained)
  offline                   QoS 1 — LWT, broker-published on ungraceful disconnect (retained)

Inbound acks (direction = ack):
  cmd_ack                   QoS 1 — reply to DEACTIVATE / ACTIVE
  uid_ack                   QoS 1 — reply to ADDUID

Key design decisions:
  - msg_id is the idempotency key; session_id is only unique per charger (charger_id, session_id)
  - session_resumed: update existing record by session_id, never create new row
  - start_epoch / stop_epoch are authoritative for billing duration
  - total_kwhr from end events is pre-computed on charger (end_meter - start_meter)
  - energy_kwh in /status is absolute PZEM meter counter — NEVER use for billing
  - heartbeat has no session_id — 60 min interval, only updates last_seen_at
  - uid_ack success: event == "uid_added" | failure: event == "uid_add_failed"
  - cmd_ack and uid_ack stored to command_logs table for audit trail
"""

import asyncio
import json
import logging
import ssl
import uuid
from datetime import datetime, timezone

import asyncpg
import aiomqtt

from app.config import settings
from app.db import TRANSIENT_DB_ERRORS
from app.services.charger_state import KEEP, record_message, mark_offline

logger = logging.getLogger(__name__)

# v6.4.0: hierarchical topics — subscribe to all evt and ack across all societies/meters/chargers
SUBSCRIBE_TOPICS = [
    ("indram/+/+/+/evt/#", 1),
    ("indram/+/+/+/ack/#", 1),
]

# Stable client ID — must never change across restarts so HiveMQ
# delivers queued QoS 1 messages when server comes back online.
# A random suffix causes HiveMQ to discard the queue on every restart.
_CLIENT_ID = "evc-server-prod"


# ------------------------------------------------------------------ #
#  TLS
# ------------------------------------------------------------------ #

def _make_tls_context() -> ssl.SSLContext | None:
    if settings.MQTT_USE_TLS:
        return ssl.create_default_context()
    return None


# ------------------------------------------------------------------ #
#  Helpers
# ------------------------------------------------------------------ #

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_device_datetime(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        try:
            return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            logger.warning("Could not parse device datetime: %s", dt_str)
            return None


def _epoch_to_dt(epoch: int | None) -> datetime | None:
    if not epoch or epoch == 0:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc)


def _coerce_fault_code(raw) -> str | None:
    """Convert fault_code to string regardless of whether charger sends int or string."""
    if raw is None:
        return None
    return str(raw)


async def _log_orphan(conn: asyncpg.Connection, charger_id: str,
                      session_id: int | None, event: str, payload: dict):
    await conn.execute(
        """
        INSERT INTO orphan_messages (charger_id, session_id, event, payload, is_reviewed)
        VALUES ($1, $2, $3, $4, FALSE)
        """,
        charger_id, session_id, event, json.dumps(payload),
    )
    logger.warning(
        "Orphan message logged | charger=%s session_id=%s event=%s",
        charger_id, session_id, event,
    )


# ------------------------------------------------------------------ #
#  Event handlers
# ------------------------------------------------------------------ #

async def handle_charging_started(conn: asyncpg.Connection, payload: dict):
    """
    Handles both new sessions and session_resumed (power-cut recovery).
    session_resumed: update existing record, never create new.
    Uses msg_id for idempotent insert (ON CONFLICT DO NOTHING).
    """
    event         = payload.get("event", "charging_started")
    charger_id    = payload["charger_id"]
    session_id    = payload["session_id"]
    msg_id        = payload.get("msg_id")
    rfid_uid      = payload.get("rfid_uid")
    start_epoch   = payload.get("start_epoch")
    start_meter   = payload.get("start_meter_kwh")
    fault_code    = _coerce_fault_code(payload.get("fault_code"))
    temperature_c = payload.get("temperature_c")
    fw_version    = payload.get("fw_version")
    offline       = bool(payload.get("offline", False))
    device_dt     = _parse_device_datetime(payload.get("datetime"))
    started_at    = _epoch_to_dt(start_epoch) or device_dt or _now()

    await record_message(conn, charger_id, payload, activity="charging")

    # ── session_resumed: power cut recovery ───────────────────────
    # Do NOT create a new session. Update the existing one by session_id.
    if event == "session_resumed":
        existing = await conn.fetchval(
            "SELECT 1 FROM charging_sessions WHERE session_id = $1 AND charger_id = $2",
            session_id, charger_id,
        )
        if existing:
            logger.info(
                "session_resumed — updating existing session | charger=%s session=%s",
                charger_id, session_id,
            )
            await conn.execute(
                """
                UPDATE charging_sessions
                SET    started_at       = COALESCE($1, started_at),
                       start_epoch      = COALESCE($2, start_epoch),
                       start_meter_kwh  = COALESCE($3, start_meter_kwh),
                       temperature_c    = COALESCE($4, temperature_c),
                       fw_version       = COALESCE($5, fw_version)
                WHERE  session_id = $6 AND charger_id = $7
                """,
                started_at, start_epoch, start_meter,
                temperature_c, fw_version, session_id, charger_id,
            )
        else:
            # Never received the original charging_started — create from resume data
            logger.info(
                "session_resumed — no existing record, creating from resume data | charger=%s session=%s",
                charger_id, session_id,
            )
            await conn.execute(
                """
                INSERT INTO charging_sessions
                    (msg_id, session_id, charger_id, rfid_uid,
                     start_kwhr, start_meter_kwh, start_epoch,
                     fault_code, temperature_c, fw_version,
                     offline, status, started_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, 'active', $12)
                ON CONFLICT DO NOTHING   -- msg_id or (charger_id, session_id) duplicate
                """,
                msg_id, session_id, charger_id, rfid_uid,
                start_meter, start_meter, start_epoch,
                fault_code, temperature_c, fw_version,
                offline, started_at,
            )
        return

    # ── Normal charging_started ───────────────────────────────────
    # Check for duplicate msg_id first
    if msg_id:
        duplicate = await conn.fetchval(
            "SELECT 1 FROM charging_sessions WHERE msg_id = $1", msg_id
        )
        if duplicate:
            logger.info("Duplicate msg_id %s — ignoring", msg_id)
            return

    # Close any orphan active session on this charger (reboot scenario)
    active = await conn.fetchrow(
        """
        SELECT session_id FROM charging_sessions
        WHERE  charger_id = $1 AND status = 'active'
        LIMIT  1
        """,
        charger_id,
    )
    if active:
        old_id = active["session_id"]
        logger.warning(
            "New charging_started while session %s still active on charger %s — closing old session",
            old_id, charger_id,
        )
        await conn.execute(
            """
            UPDATE charging_sessions
            SET status = 'charging_ended', ended_at = $1
            WHERE session_id = $2 AND charger_id = $3 AND status = 'active'
            """,
            _now(), old_id, charger_id,
        )

    # Insert new session
    await conn.execute(
        """
        INSERT INTO charging_sessions
            (msg_id, session_id, charger_id, rfid_uid,
             start_kwhr, start_meter_kwh, start_epoch,
             fault_code, temperature_c, fw_version,
             offline, status, started_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, 'active', $12)
        ON CONFLICT DO NOTHING   -- msg_id or (charger_id, session_id) duplicate
        """,
        msg_id, session_id, charger_id, rfid_uid,
        start_meter, start_meter, start_epoch,
        fault_code, temperature_c, fw_version,
        offline, started_at,
    )
    logger.info(
        "charging_started | charger=%s session=%s msg_id=%s rfid=%s offline=%s",
        charger_id, session_id, msg_id, rfid_uid, offline,
    )


async def handle_charging_ended(conn: asyncpg.Connection, payload: dict, status: str):
    """
    Handles charging_ended, charging_ended_error, charging_stopped_by_admin.
    Uses msg_id for idempotent insert / stop_epoch for accurate billing.
    total_kwhr from the charger is pre-computed (end_meter - start_meter).
    Safe to replay — UPDATE WHERE status='active' is a no-op on closed sessions.
    """
    charger_id    = payload["charger_id"]
    session_id    = payload["session_id"]
    msg_id        = payload.get("msg_id")
    total_kwhr    = payload.get("total_kwhr")
    stop_epoch    = payload.get("stop_epoch")
    start_epoch   = payload.get("start_epoch")
    end_meter     = payload.get("end_meter_kwh")
    start_meter   = payload.get("start_meter_kwh")
    fault_code    = _coerce_fault_code(payload.get("fault_code"))
    temperature_c = payload.get("temperature_c")
    fw_version    = payload.get("fw_version")
    offline       = bool(payload.get("offline", False))
    device_dt     = _parse_device_datetime(payload.get("datetime"))

    # Authoritative end time: stop_epoch → device datetime → server time
    ended_at = _epoch_to_dt(stop_epoch) or device_dt or _now()

    # Validate epoch sanity
    if start_epoch and stop_epoch:
        duration_sec = stop_epoch - start_epoch
        if duration_sec < 0:
            logger.warning(
                "stop_epoch < start_epoch on charger=%s session=%s — flagging",
                charger_id, session_id,
            )
        elif duration_sec > 86400:
            logger.warning(
                "Session duration > 24h on charger=%s session=%s (%s s) — flagging",
                charger_id, session_id, duration_sec,
            )

    # Validate total_kwhr
    if total_kwhr is not None and (total_kwhr < 0 or total_kwhr > 50):
        logger.warning(
            "Suspicious total_kwhr=%.4f on charger=%s session=%s — possible meter rollover",
            total_kwhr, charger_id, session_id,
        )

    if status == "charging_ended_error":
        await record_message(conn, charger_id, payload, activity="idle", fault=fault_code)
    elif status == "charging_stopped_by_admin":
        await record_message(conn, charger_id, payload, activity="idle", locked=True)
    else:
        await record_message(conn, charger_id, payload, activity="idle")

    session = await conn.fetchrow(
        "SELECT session_id FROM charging_sessions WHERE session_id = $1 AND charger_id = $2",
        session_id, charger_id,
    )
    if not session:
        await _log_orphan(conn, charger_id, session_id, status, payload)
        return

    updated = await conn.execute(
        """
        UPDATE charging_sessions
        SET    status          = $1,
               msg_id          = COALESCE(msg_id, $2),
               end_kwhr        = $3,
               units_consumed  = $4,
               stop_epoch      = $5,
               end_meter_kwh   = $6,
               start_meter_kwh = COALESCE(start_meter_kwh, $7),
               start_epoch     = COALESCE(start_epoch, $8),
               fault_code      = $9,
               temperature_c   = COALESCE($10, temperature_c),
               fw_version      = COALESCE($11, fw_version),
               offline         = offline OR $12,
               ended_at        = $13
        WHERE  session_id = $14
          AND  charger_id = $15
          AND  status = 'active'
        """,
        status, msg_id, end_meter, total_kwhr,
        stop_epoch, end_meter, start_meter, start_epoch,
        fault_code, temperature_c, fw_version, offline,
        ended_at, session_id, charger_id,
    )
    logger.info(
        "charging_ended [%s] | charger=%s session=%s msg_id=%s units=%.4f offline=%s",
        status, charger_id, session_id, msg_id,
        total_kwhr or 0, offline,
    )


# ── Society-wide (DEACTIVATE_ALL / ACTIVATE_ALL) queue ────────────────────
# One pending_commands row per charger, status 'pending' until the charger
# confirms. When a charger that missed the broadcast shows up again (online /
# status / heartbeat) the society command is re-broadcast. It's idempotent, so
# chargers that already applied it just ack again, and the lock reason stays
# 'society' — no per-charger 'billing' lock for ACTIVATE_ALL to trip over.

BULK_CMDS        = ("DEACTIVATE_ALL", "ACTIVATE_ALL")
BULK_FOR_SINGLE  = {"DEACTIVATE": "DEACTIVATE_ALL", "ACTIVE": "ACTIVATE_ALL"}   # ack of ACTIVE follow-up → bulk row
RETRY_MIN_GAP_S  = 60    # don't re-broadcast more often than this per society + command


async def _rebroadcast_bulk(conn: asyncpg.Connection, charger_id: str, bulk_cmd: str) -> bool:
    """Re-broadcast a queued society command because one of its chargers is back online."""
    society_id = await conn.fetchval(
        """
        SELECT m.society_id
        FROM   chargers c JOIN meters m ON m.id = c.meter_id
        WHERE  c.charger_id = $1
        """,
        charger_id,
    )
    if society_id is None:
        return False
    from app import mqtt_commands
    send = mqtt_commands.send_deactivate_all if bulk_cmd == "DEACTIVATE_ALL" else mqtt_commands.send_activate_all
    try:
        await send(society_id)
    except Exception as e:   # broker hiccup — next online/status retries
        logger.error("Bulk re-broadcast failed | charger=%s society=%s cmd=%s error=%s",
                     charger_id, society_id, bulk_cmd, e)
        return False
    now = _now()
    await conn.execute(
        """
        UPDATE pending_commands SET attempts = attempts + 1, last_sent_at = $1
        WHERE  charger_id = $2 AND cmd = $3 AND status = 'pending'
        """,
        now, charger_id, bulk_cmd,
    )
    # The broadcast reached every charger in the society — start the gap for all
    # still-pending rows so several chargers reconnecting together don't each re-broadcast
    await conn.execute(
        """
        UPDATE pending_commands SET last_sent_at = $1
        WHERE  society_id = $2 AND cmd = $3 AND status = 'pending'
        """,
        now, society_id, bulk_cmd,
    )
    return True


async def _send_single_for_bulk(conn: asyncpg.Connection, charger_id: str, bulk_cmd: str) -> bool:
    """Send the per-charger DEACTIVATE / ACTIVE that matches a queued society command.
    Only used for the ACTIVATE_ALL still_locked follow-up — retries re-broadcast instead."""
    target = await conn.fetchrow(
        """
        SELECT m.society_id, c.meter_id
        FROM   chargers c JOIN meters m ON m.id = c.meter_id
        WHERE  c.charger_id = $1
        """,
        charger_id,
    )
    if not target:
        return False
    from app import mqtt_commands
    send = mqtt_commands.send_deactivate if bulk_cmd == "DEACTIVATE_ALL" else mqtt_commands.send_active
    try:
        await send(charger_id, target["society_id"], target["meter_id"])
    except Exception as e:   # broker hiccup — next heartbeat retries
        logger.error("Per-charger send failed | charger=%s queued=%s error=%s", charger_id, bulk_cmd, e)
        return False
    await conn.execute(
        """
        UPDATE pending_commands SET attempts = attempts + 1, last_sent_at = $1
        WHERE  charger_id = $2 AND cmd = $3 AND status = 'pending'
        """,
        _now(), charger_id, bulk_cmd,
    )
    return True


async def _resolve_bulk(conn: asyncpg.Connection, charger_id: str, bulk_cmd: str,
                        ok: bool, reason: str | None, now, from_broadcast: bool = False):
    """Apply a charger's answer (cmd_ack or heartbeat lock state) to its pending bulk row."""
    # Re-broadcasts reach chargers that already resolved — their repeat acks change nothing
    pending = await conn.fetchval(
        """
        SELECT 1 FROM pending_commands
        WHERE  charger_id = $1 AND cmd = $2 AND status = 'pending'
        LIMIT  1
        """,
        charger_id, bulk_cmd,
    )
    if not pending:
        logger.debug("Bulk ack with no pending row — ignored | charger=%s cmd=%s", charger_id, bulk_cmd)
        return

    if not ok:
        # stale_cmd / clock_invalid / replay_detected / auth_failed … — keep pending, retry on next heartbeat
        await conn.execute(
            """
            UPDATE pending_commands SET reason = $1
            WHERE  charger_id = $2 AND cmd = $3 AND status = 'pending'
            """,
            reason, charger_id, bulk_cmd,
        )
        return

    # ACTIVATE_ALL only removes the society lock. If the charger still reports a lock
    # it may carry a 'billing' lock from the heartbeat retry — send a per-charger ACTIVE
    # to clear it and wait for that ack. (The ACTIVE ack resolves the row, so no loop:
    # a lock that ACTIVE can't clear, e.g. tamper, ends as 'still_locked'.)
    if bulk_cmd == "ACTIVATE_ALL" and from_broadcast and reason == "still_locked":
        if await _send_single_for_bulk(conn, charger_id, bulk_cmd):
            logger.info("ACTIVATE_ALL still_locked — sent ACTIVE follow-up | charger=%s", charger_id)
            return

    resolved = await conn.execute(
        """
        UPDATE pending_commands
        SET    status = 'done', reason = $1, resolved_at = $2
        WHERE  charger_id = $3 AND cmd = $4 AND status = 'pending'
        """,
        reason, now, charger_id, bulk_cmd,
    )
    if bulk_cmd == "DEACTIVATE_ALL":
        await conn.execute("UPDATE chargers SET is_active = FALSE WHERE charger_id = $1", charger_id)
    elif reason != "still_locked":
        await conn.execute("UPDATE chargers SET is_active = TRUE WHERE charger_id = $1", charger_id)
    logger.info("Bulk command resolved | charger=%s cmd=%s reason=%s (%s)",
                charger_id, bulk_cmd, reason, resolved)


async def _retry_bulk_commands(conn: asyncpg.Connection, charger_id: str, payload: dict):
    """Called on online / status / heartbeat — the charger is reachable, so push any queued society command."""
    row = await conn.fetchrow(
        """
        SELECT id, cmd, last_sent_at
        FROM   pending_commands
        WHERE  charger_id = $1 AND cmd = ANY($2::text[]) AND status = 'pending'
        ORDER  BY created_at DESC
        LIMIT  1
        """,
        charger_id, list(BULK_CMDS),
    )
    if not row:
        return

    now = _now()
    bulk_cmd = row["cmd"]

    # Heartbeat reports lock state — if it already matches, no need to send anything
    locked  = payload.get("locked")
    reasons = set(payload.get("lock_reasons") or [])
    if bulk_cmd == "DEACTIVATE_ALL" and locked is True and "society" in reasons:
        await _resolve_bulk(conn, charger_id, bulk_cmd, True, None, now)
        return
    if bulk_cmd == "ACTIVATE_ALL" and locked is False:
        await _resolve_bulk(conn, charger_id, bulk_cmd, True, None, now)
        return

    last_sent = row["last_sent_at"]
    if last_sent and (now - last_sent).total_seconds() < RETRY_MIN_GAP_S:
        return

    if not await _rebroadcast_bulk(conn, charger_id, bulk_cmd):
        return
    logger.info("Bulk command re-broadcast | charger=%s cmd=%s", charger_id, bulk_cmd)


async def handle_heartbeat(conn: asyncpg.Connection, payload: dict):
    """
    Keep-alive: every 60 min (hub / direct charger), every 5 min (mesh node).
    status: available | charging | fault · fault_code: E09 locked, E08 too hot, E04 meter, null
    locked + lock_reasons (billing / society / tamper).
    """
    charger_id     = payload["charger_id"]
    charger_status = payload.get("status")   # "available" | "charging" | "fault"
    fault_code     = _coerce_fault_code(payload.get("fault_code"))
    temperature_c  = payload.get("temperature_c")

    await record_message(
        conn, charger_id, payload,
        activity="charging" if charger_status == "charging" else "idle",
        fault=fault_code,   # E09 is a lock, not a fault — record_message keeps only blocking faults
        locked=payload.get("locked", KEEP), lock_reasons=payload.get("lock_reasons", KEEP),
    )
    await _retry_bulk_commands(conn, charger_id, payload)

    logger.debug(
        "heartbeat | charger=%s status=%s fault=%s temp=%s",
        charger_id, charger_status, fault_code, temperature_c,
    )


async def handle_status(conn: asyncpg.Connection, payload: dict):
    """
    Live telemetry snapshot — retained, published every 30s during sessions.
    energy_kwh is the ABSOLUTE PZEM meter counter — NOT session energy.
    Upserts a single row per charger in charger_status table.
    """
    charger_id     = payload.get("charger_id")
    charger_status = payload.get("charger_status")
    voltage        = payload.get("voltage")
    current        = payload.get("current")
    energy_kwh     = payload.get("energy_kwh")   # absolute meter, NOT session energy
    rfid_uid       = payload.get("rfid_uid")
    duration_min   = payload.get("duration_min")
    fault_code     = _coerce_fault_code(payload.get("fault_code"))
    temperature_c  = payload.get("temperature_c")
    device_dt      = _parse_device_datetime(payload.get("datetime"))

    if not charger_id:
        logger.warning("Status message missing charger_id — skipping")
        return

    # charger_status: active | idle | fault · fault_code: 200/0 normal, 504 meter stopped, 505 meter back
    await record_message(
        conn, charger_id, payload,
        activity={"active": "charging", "idle": "idle"}.get(charger_status, KEEP),
        fault="504" if fault_code == "504" else KEEP,
        clear_faults=("504", "E04") if fault_code in ("505", "200", "0", None) else (),
    )

    await conn.execute(
        """
        INSERT INTO charger_status
            (charger_id, charger_status, voltage, current, energy_kwh,
             rfid_uid, duration_min, fault_code, received_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        ON CONFLICT (charger_id) DO UPDATE
            SET charger_status  = EXCLUDED.charger_status,
                voltage         = EXCLUDED.voltage,
                current         = EXCLUDED.current,
                energy_kwh      = EXCLUDED.energy_kwh,
                rfid_uid        = EXCLUDED.rfid_uid,
                duration_min    = EXCLUDED.duration_min,
                fault_code      = EXCLUDED.fault_code,
                received_at     = EXCLUDED.received_at
        """,
        charger_id, charger_status, voltage, current, energy_kwh,
        rfid_uid, duration_min, fault_code, _now(),
    )
    # A retained replay is the broker's old copy — the charger may not be reachable
    if not payload.get("_retained"):
        await _retry_bulk_commands(conn, charger_id, payload)
    logger.debug(
        "status | charger=%s status=%s voltage=%s current=%s energy_kwh=%s temp=%s",
        charger_id, charger_status, voltage, current, energy_kwh, temperature_c,
    )


async def handle_online(conn: asyncpg.Connection, payload: dict):
    """
    Published by the charger on (re)connect. Push any society command it
    missed while offline right away instead of waiting for the next status.
    """
    charger_id = payload.get("charger_id")
    if not charger_id:
        logger.warning("Online message missing charger_id — skipping")
        return

    await record_message(
        conn, charger_id, payload,
        locked=payload.get("locked", KEEP), lock_reasons=payload.get("lock_reasons", KEEP),
        reset_reason=payload.get("reset_reason"),
    )
    await _retry_bulk_commands(conn, charger_id, payload)
    logger.info("charger online | charger=%s fw=%s reset=%s", charger_id,
                payload.get("fw_version"), payload.get("reset_reason"))


async def handle_cmd_ack(conn: asyncpg.Connection, payload: dict):
    """
    Handles cmd_ack from charger for DEACTIVATE and ACTIVE commands.
    Looks up the pending_commands row and applies DB state changes.
    Works even if the original API request already timed out —
    the subscriber applies changes silently in the background.
    Multi-instance safe: all state is in PostgreSQL.
    """
    charger_id = payload.get("charger_id")
    cmd        = payload.get("cmd")
    ok         = payload.get("ok")
    reason     = payload.get("reason")
    fw_version = payload.get("fw_version")
    now        = _now()

    if not ok:
        logger.warning("Command REJECTED | charger=%s cmd=%s reason=%s", charger_id, cmd, reason)
    else:
        logger.info("Command ACK ok | charger=%s cmd=%s", charger_id, cmd)

    # Log to audit trail
    await conn.execute(
        """
        INSERT INTO command_logs
            (charger_id, log_type, cmd, ok, reason, fw_version, received_at)
        VALUES ($1, 'cmd_ack', $2, $3, $4, $5, $6)
        """,
        charger_id, cmd, ok, reason, fw_version, now,
    )

    await _record_cmd_lock(conn, charger_id, payload, cmd, ok, reason)

    # Skip ADDUID — handled separately in handle_uid_ack
    if cmd == "ADDUID":
        return

    # Society-wide commands: ack from the broadcast itself
    if cmd in BULK_CMDS:
        await _resolve_bulk(conn, charger_id, cmd, bool(ok), reason, now, from_broadcast=True)
        return

    # Ack of a per-charger retry (DEACTIVATE / ACTIVE) that was queued as a bulk command
    if cmd in BULK_FOR_SINGLE:
        await _resolve_bulk(conn, charger_id, BULK_FOR_SINGLE[cmd], bool(ok), reason, now)

    # DELUID — success is decided by uid_ack; only a rejection is final here
    if cmd == "DELUID":
        if not ok:
            await conn.execute(
                """
                UPDATE pending_commands
                SET    status = 'failed', reason = $1, resolved_at = $2
                WHERE  id = (
                    SELECT id FROM pending_commands
                    WHERE  charger_id = $3 AND cmd = 'DELUID' AND status = 'pending'
                    ORDER  BY created_at DESC LIMIT 1
                )
                """,
                "rejected_by_charger", now, charger_id,
            )
        return

    # Find the most recent pending command for this charger+cmd
    pending = await conn.fetchrow(
        """
        SELECT id, flat_id, status
        FROM   pending_commands
        WHERE  charger_id = $1
          AND  cmd        = $2
          AND  status     = 'pending'
        ORDER  BY created_at DESC
        LIMIT  1
        """,
        charger_id, cmd,
    )

    if not pending:
        logger.debug(
            "cmd_ack received but no pending command found | charger=%s cmd=%s "
            "(may have timed out — applying state change anyway)",
            charger_id, cmd,
        )
        # Still apply state change even if API already timed out
        if ok:
            await _apply_cmd_state(conn, charger_id, cmd, flat_id=None)
        return

    flat_id = pending["flat_id"]

    # Update pending command status
    new_status = "done" if ok else "failed"
    await conn.execute(
        """
        UPDATE pending_commands
        SET    status = $1, reason = $2, resolved_at = $3
        WHERE  id = $4
        """,
        new_status, reason, now, pending["id"],
    )

    # Apply actual DB state change if command succeeded
    if ok:
        await _apply_cmd_state(conn, charger_id, cmd, flat_id)


LOCK_FOR_CMD = {"DEACTIVATE": "billing", "DEACTIVATE_ALL": "society"}
UNLOCK_FOR_CMD = {"ACTIVE": "billing", "ACTIVATE_ALL": "society"}


async def _record_cmd_lock(conn: asyncpg.Connection, charger_id: str, payload: dict,
                           cmd: str | None, ok, reason: str | None):
    """A confirmed (de)activate changes the charger's lock; any ack counts as contact."""
    if ok and cmd in LOCK_FOR_CMD:
        await record_message(conn, charger_id, payload, activity="idle", add_reason=LOCK_FOR_CMD[cmd])
    elif ok and cmd in UNLOCK_FOR_CMD:
        if reason == "still_locked":   # another lock (e.g. tamper) keeps it off
            await record_message(conn, charger_id, payload, remove_reason=UNLOCK_FOR_CMD[cmd], locked=True)
        else:
            await record_message(conn, charger_id, payload, remove_reason=UNLOCK_FOR_CMD[cmd])
    else:
        await record_message(conn, charger_id, payload)


async def _apply_cmd_state(conn: asyncpg.Connection, charger_id: str,
                            cmd: str, flat_id: int | None):
    """Apply RFID card state changes after confirmed cmd_ack."""
    if cmd == "DEACTIVATE":
        if flat_id:
            await conn.execute(
                "UPDATE rfid_cards SET is_active = FALSE WHERE flat_id = $1",
                flat_id,
            )
        else:
            # flat_id unknown (late ack after timeout) — find via charger
            await conn.execute(
                """
                UPDATE rfid_cards SET is_active = FALSE
                WHERE  flat_id = (
                    SELECT f.id FROM flats f
                    JOIN   chargers c ON c.flat_id = f.id
                    WHERE  c.charger_id = $1
                )
                """,
                charger_id,
            )
        logger.info("Applied DEACTIVATE state | charger=%s flat_id=%s", charger_id, flat_id)

    elif cmd == "ACTIVE":
        if flat_id:
            await conn.execute(
                "UPDATE rfid_cards SET is_active = TRUE WHERE flat_id = $1",
                flat_id,
            )
        else:
            await conn.execute(
                """
                UPDATE rfid_cards SET is_active = TRUE
                WHERE  flat_id = (
                    SELECT f.id FROM flats f
                    JOIN   chargers c ON c.flat_id = f.id
                    WHERE  c.charger_id = $1
                )
                """,
                charger_id,
            )
        logger.info("Applied ACTIVE state | charger=%s flat_id=%s", charger_id, flat_id)


async def _handle_deluid_ack(conn: asyncpg.Connection, payload: dict):
    """
    uid_ack for DELUID. The card is deleted from the DB only here, after the
    charger confirms (or reports the UID was not on it).
    """
    charger_id = payload.get("charger_id")
    event      = payload.get("event")
    rfid_uid   = payload.get("rfid_uid")
    reason     = payload.get("reason")
    fw_version = payload.get("fw_version")
    now        = _now()

    removed = event == "uid_removed" or (
        event == "uid_remove_failed" and reason == "not_found"
    )

    await conn.execute(
        """
        INSERT INTO command_logs
            (charger_id, log_type, cmd, ok, reason, rfid_uid, fw_version, received_at)
        VALUES ($1, 'uid_ack', 'DELUID', $2, $3, $4, $5, $6)
        """,
        charger_id, removed, reason, rfid_uid, fw_version, now,
    )

    # 'timeout' is accepted so a late confirmation still brings the DB in line
    pending = await conn.fetchrow(
        """
        SELECT id
        FROM   pending_commands
        WHERE  charger_id = $1
          AND  cmd        = 'DELUID'
          AND  rfid_uid   = $2
          AND  status     IN ('pending', 'timeout')
        ORDER  BY created_at DESC
        LIMIT  1
        """,
        charger_id, rfid_uid,
    )
    if not pending:
        logger.info("DELUID uid_ack with no pending command | charger=%s uid=%s", charger_id, rfid_uid)
        return

    await conn.execute(
        "UPDATE pending_commands SET status = $1, reason = $2, resolved_at = $3 WHERE id = $4",
        "done" if removed else "failed", reason, now, pending["id"],
    )
    if removed:
        await conn.execute("DELETE FROM rfid_cards WHERE uid = $1", rfid_uid)
        logger.info("DELUID confirmed — card %s deleted | charger=%s", rfid_uid, charger_id)
    else:
        logger.warning("DELUID FAILED | charger=%s uid=%s reason=%s", charger_id, rfid_uid, reason)


async def handle_uid_ack(conn: asyncpg.Connection, payload: dict):
    """
    Handles uid_ack from charger for ADDUID command.
    Looks up pending_commands and applies DB state changes.
    On success: sets rfid_card.is_active = True.
    On failure: deletes the rfid_card record.
    Works even if the original API request already timed out —
    late delivery still corrects the DB state silently.
    Multi-instance safe: all state is in PostgreSQL.
    """
    charger_id      = payload.get("charger_id")
    event           = payload.get("event")
    rfid_uid        = payload.get("rfid_uid")
    reason          = payload.get("reason")
    slots_remaining = payload.get("slots_remaining")
    fw_version      = payload.get("fw_version")
    now             = _now()
    success         = event == "uid_added"

    await record_message(conn, charger_id, payload)

    if event in ("uid_removed", "uid_remove_failed"):
        await _handle_deluid_ack(conn, payload)
        return

    if not success:
        logger.warning("ADDUID FAILED | charger=%s uid=%s reason=%s", charger_id, rfid_uid, reason)
    else:
        logger.info("ADDUID SUCCESS | charger=%s uid=%s slots_remaining=%s", charger_id, rfid_uid, slots_remaining)

    # Log to audit trail
    await conn.execute(
        """
        INSERT INTO command_logs
            (charger_id, log_type, cmd, ok, reason,
             rfid_uid, slots_remaining, fw_version, received_at)
        VALUES ($1, 'uid_ack', 'ADDUID', $2, $3, $4, $5, $6, $7)
        """,
        charger_id, success, reason,
        rfid_uid, slots_remaining, fw_version, now,
    )

    # Find the pending ADDUID command for this charger+uid
    pending = await conn.fetchrow(
        """
        SELECT id, rfid_card_id, flat_id
        FROM   pending_commands
        WHERE  charger_id = $1
          AND  cmd        = 'ADDUID'
          AND  rfid_uid   = $2
          AND  status     = 'pending'
        ORDER  BY created_at DESC
        LIMIT  1
        """,
        charger_id, rfid_uid,
    )

    new_status = "done" if success else "failed"

    if pending:
        await conn.execute(
            """
            UPDATE pending_commands
            SET    status = $1, reason = $2, resolved_at = $3
            WHERE  id = $4
            """,
            new_status, reason, now, pending["id"],
        )
        rfid_card_id = pending["rfid_card_id"]
    else:
        # No pending row — late ack after API timeout
        # Find the card by uid
        logger.info(
            "uid_ack received but no pending command found | charger=%s uid=%s "
            "(late delivery — applying state anyway)",
            charger_id, rfid_uid,
        )
        row = await conn.fetchrow(
            "SELECT id FROM rfid_cards WHERE uid = $1", rfid_uid
        )
        rfid_card_id = row["id"] if row else None

    if rfid_card_id:
        if success:
            await conn.execute(
                "UPDATE rfid_cards SET is_active = TRUE WHERE id = $1",
                rfid_card_id,
            )
            logger.info("ADDUID confirmed — card %s activated | charger=%s", rfid_card_id, charger_id)
        else:
            # Charger rejected — remove from DB
            await conn.execute(
                "DELETE FROM rfid_cards WHERE id = $1 AND is_active = FALSE",
                rfid_card_id,
            )
            logger.info("ADDUID failed — card %s removed from DB | charger=%s reason=%s",
                        rfid_card_id, charger_id, reason)


# ------------------------------------------------------------------ #
#  Message router
# ------------------------------------------------------------------ #

async def handle_offline(conn: asyncpg.Connection, payload: dict):
    """
    LWT — broker publishes this when charger disconnects ungracefully.
    Topic is retained — new subscribers immediately see the offline state.
    """
    charger_id = payload.get("charger_id")
    if not charger_id:
        logger.warning("Offline LWT missing charger_id — skipping")
        return
    if payload.get("_retained"):
        # Replayed on (re)subscribe — it may predate the charger coming back online.
        # The silent-charger sweep marks it offline if it really is gone.
        logger.debug("Retained offline replay ignored | charger=%s", charger_id)
        return

    await mark_offline(conn, charger_id)

    await conn.execute(
        """
        INSERT INTO charger_status (charger_id, charger_status, received_at)
        VALUES ($1, 'offline', $2)
        ON CONFLICT (charger_id) DO UPDATE
            SET charger_status = 'offline',
                received_at    = EXCLUDED.received_at
        """,
        charger_id, _now(),
    )
    logger.info("charger offline (LWT) | charger=%s", charger_id)


async def handle_handshake_ack(conn: asyncpg.Connection | None, payload: dict):
    """
    Handles ack/handshake from charger.
    Pure in-memory operation — resolves the waiter keyed on request_id.
    conn is None when called from the fast-path in process_message.
    last_seen_at is NOT updated here — heartbeat and status messages do that.
    """
    charger_id = payload.get("charger_id")
    request_id = payload.get("request_id")
    fw_version = payload.get("fw_version")

    if not request_id:
        logger.warning("handshake_ack missing request_id | charger=%s", charger_id)
        return

    # Resolve waiter — wakes up the HTTP request waiting in rfid.py
    from app.ack_waiters import resolve_handshake
    resolve_handshake(request_id, payload)

    logger.info("handshake_ack | charger=%s request_id=%s online=%s temp=%s fw=%s",
                charger_id, request_id,
                payload.get("online"), payload.get("temperature_c"), fw_version)


# ── Message router maps ─────────────────────────────────────────────

# evt/* topics — charger events
EVT_HANDLER_MAP = {
    "charging_started":          lambda conn, p: handle_charging_started(conn, p),
    "session_resumed":           lambda conn, p: handle_charging_started(conn, p),
    "charging_ended":            lambda conn, p: handle_charging_ended(conn, p, "charging_ended"),
    "charging_ended_error":      lambda conn, p: handle_charging_ended(conn, p, "charging_ended_error"),
    "charging_stopped_by_admin": lambda conn, p: handle_charging_ended(conn, p, "charging_stopped_by_admin"),
    "heartbeat":                 lambda conn, p: handle_heartbeat(conn, p),
    "status":                    lambda conn, p: handle_status(conn, p),
    "online":                    lambda conn, p: handle_online(conn, p),
    "offline":                   lambda conn, p: handle_offline(conn, p),
}

# ack/* topics — charger responses to server commands
ACK_HANDLER_MAP = {
    "cmd_ack":   lambda conn, p: handle_cmd_ack(conn, p),
    "uid_ack":   lambda conn, p: handle_uid_ack(conn, p),
    "handshake": lambda conn, p: handle_handshake_ack(conn, p),
}


async def process_message(pool: asyncpg.Pool, topic: str, raw_payload: bytes, retained: bool = False):
    # New topic structure: indram/{society_id}/{meter_id}/{charger_id}/{direction}/{event}
    # e.g. indram/2/4/EZC001/evt/charging_started
    parts = topic.split("/")
    if len(parts) < 6 or parts[0] != "indram":
        logger.error("Unexpected topic format: %s", topic)
        return

    direction  = parts[4]   # "evt" or "ack"
    event      = parts[5]   # charging_started, heartbeat, cmd_ack, etc.

    # Empty payload = a retained message being cleared (firmware 6.5.3's offline always has a body)
    if not raw_payload or not raw_payload.strip():
        logger.debug("Empty payload ignored | topic=%s", topic)
        return
    else:
        try:
            payload: dict = json.loads(raw_payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error("Failed to decode MQTT payload | topic=%s error=%s", topic, e)
            return

    payload["_retained"] = retained   # broker replay of a retained message, not live contact

    if direction == "evt":
        handler     = EVT_HANDLER_MAP.get(event)
        needs_db    = True
    elif direction == "ack":
        if event == "handshake":
            # Handshake ack is pure in-memory — no DB needed
            # Resolve the waiter directly without acquiring a connection
            try:
                await handle_handshake_ack(None, payload)
            except Exception as e:
                logger.exception("Error handling ack/handshake | topic=%s | %s", topic, e)
            return
        handler  = ACK_HANDLER_MAP.get(event)
        needs_db = True
    else:
        logger.warning("Unknown direction '%s' in topic '%s'", direction, topic)
        return

    if not handler:
        logger.warning("No handler for %s/%s | topic=%s", direction, event, topic)
        return

    async with pool.acquire(timeout=DB_ACQUIRE_TIMEOUT_S) as conn:
        async with conn.transaction():
            try:
                await handler(conn, payload)
            except TRANSIENT_DB_ERRORS:
                raise   # retried by _process_reliably
            except Exception as e:
                logger.exception(
                    "Error handling %s/%s | topic=%s | %s", direction, event, topic, e
                )
                raise


# ── Reliable processing ───────────────────────────────────────────────
# After a crash or a database blip the broker delivers a backlog all at once
# (clean_session=False). Each message is retried while the database is unreachable,
# at most MAX_CONCURRENT run at once (≈ the pool size), and one charger's messages
# are handled one at a time in arrival order — a retried START never lands after
# its END. Every handler is idempotent (msg_id / status guards), so a retry is safe.

MAX_CONCURRENT       = 8
DB_ACQUIRE_TIMEOUT_S = 10
RETRY_DELAYS_S       = (1, 2, 4, 8, 16)


_slots: asyncio.Semaphore | None = None
_charger_locks: dict[str, asyncio.Lock] = {}
_in_flight: set[asyncio.Task] = set()


def _charger_lock(topic: str) -> asyncio.Lock:
    parts = topic.split("/")
    key = parts[3] if len(parts) > 3 else topic
    if key not in _charger_locks:
        _charger_locks[key] = asyncio.Lock()
    return _charger_locks[key]


def _describe(raw_payload: bytes) -> str:
    try:
        return json.loads(raw_payload).get("msg_id") or ""
    except Exception:
        return ""


async def _process_reliably(pool: asyncpg.Pool, topic: str, raw_payload: bytes, retained: bool):
    global _slots
    if _slots is None:
        _slots = asyncio.Semaphore(MAX_CONCURRENT)
    async with _charger_lock(topic), _slots:
        for attempt in range(len(RETRY_DELAYS_S) + 1):
            try:
                await process_message(pool, topic, raw_payload, retained)
                if attempt:
                    logger.info("Processed after %s retr%s | topic=%s", attempt, "y" if attempt == 1 else "ies", topic)
                return
            except TRANSIENT_DB_ERRORS as e:
                if attempt == len(RETRY_DELAYS_S):
                    logger.error("Message DROPPED — database unreachable after %s attempts | topic=%s msg_id=%s | %s: %s",
                                 attempt + 1, topic, _describe(raw_payload), type(e).__name__, e)
                    return
                delay = RETRY_DELAYS_S[attempt]
                logger.warning("Database unreachable — retrying in %ss | topic=%s | %s",
                               delay, topic, type(e).__name__)
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                raise
            except Exception:
                return   # a bug or bad payload — already logged with its traceback; retrying won't help


def _spawn_message(pool: asyncpg.Pool, topic: str, raw_payload: bytes, retained: bool):
    task = asyncio.create_task(_process_reliably(pool, topic, raw_payload, retained))
    _in_flight.add(task)
    task.add_done_callback(_in_flight.discard)


# ------------------------------------------------------------------ #
#  Main subscriber loop
# ------------------------------------------------------------------ #

async def run_mqtt_subscriber(pool: asyncpg.Pool):
    tls_context = _make_tls_context()
    backoff     = 5

    while True:
        try:
            logger.info(
                "Connecting to MQTT broker at %s:%s (TLS=%s client_id=%s)",
                settings.MQTT_HOST, settings.MQTT_PORT,
                settings.MQTT_USE_TLS, _CLIENT_ID,
            )
            async with aiomqtt.Client(
                hostname=settings.MQTT_HOST,
                port=settings.MQTT_PORT,
                username=settings.MQTT_USERNAME or None,
                password=settings.MQTT_PASSWORD or None,
                tls_context=tls_context,
                identifier=_CLIENT_ID,
                clean_session=False,   # persist session — HiveMQ queues QoS 1 msgs while offline
                keepalive=30,
            ) as client:
                for topic_filter, qos in SUBSCRIBE_TOPICS:
                    await client.subscribe(topic_filter, qos=qos)
                    logger.info("MQTT subscribed to '%s' QoS %s", topic_filter, qos)
                backoff = 5

                async for message in client.messages:
                    _spawn_message(pool, str(message.topic), message.payload, bool(message.retain))

        except aiomqtt.MqttError as e:
            logger.error("MQTT connection lost: %s — reconnecting in %ss", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

        except asyncio.CancelledError:
            logger.info("MQTT subscriber cancelled — shutting down cleanly")
            raise

        except Exception as e:
            logger.exception("Unexpected MQTT error: %s — reconnecting in %ss", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)