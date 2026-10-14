"""
app/services/charger_state.py
-----------------------------
Keeps chargers.status accurate from the messages chargers send (firmware 6.5.3).

status — what both charger pages show:
  charging         a session is running
  available        idle, ready for a card
  locked           blocked: billing (Deactivate), society (Deactivate all) or tamper — see lock_reasons
  fault            blocked by a fault: E04 meter not responding, E08 too hot, 504 meter stopped
  offline          broker sent offline, or silent too long (75 min hub/direct, 12 min mesh node)
  never_connected  no message yet

Every message from the charger itself counts as contact (last_seen_at, back from offline).
Its state fields are applied only when the message is live: copies resent from the charger's
memory ("offline": true, possibly days old) and retained replays from the broker never
overwrite the current state.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

import asyncpg

from app.db import TRANSIENT_DB_ERRORS

logger = logging.getLogger(__name__)

BLOCKING_FAULTS  = {"E04", "E08", "504"}     # no new sessions until cleared
SILENT_LIMIT_MIN = {"hub": 75, "mesh": 12}   # no message for this long = offline
SWEEP_EVERY_S    = 300
SWEEP_RETRY_S    = 30

KEEP = object()   # "this message says nothing about that field"


def resolve_status(activity: str, fault: str | None, locked: bool) -> str:
    """Most important first: a fault or a lock blocks charging; otherwise charging / available."""
    if fault in BLOCKING_FAULTS:
        return "fault"
    if locked:
        return "locked"
    return "charging" if activity == "charging" else "available"


def _reasons(raw) -> list[str]:
    if raw is None:
        return []
    return list(json.loads(raw) if isinstance(raw, str) else raw)


async def record_message(
    conn: asyncpg.Connection,
    charger_id: str,
    payload: dict,
    *,
    activity=KEEP,          # "charging" | "idle"
    fault=KEEP,             # a code, or None to clear
    clear_faults=(),        # clear the fault only if it is one of these (status 505 / 200)
    locked=KEEP,            # bool
    lock_reasons=KEEP,      # full list from the charger
    add_reason: str | None = None,
    remove_reason: str | None = None,
    reset_reason: str | None = None,
) -> str | None:
    """Record a message from the charger and recompute its status. Returns the new status."""
    if payload.get("_retained"):
        return None   # broker replay of an old message — not contact, not current state

    row = await conn.fetchrow(
        "SELECT status, fault_code, locked, lock_reasons FROM chargers WHERE charger_id = $1 FOR UPDATE",
        charger_id,
    )
    if row is None:
        return None

    new_fault, new_locked, reasons = row["fault_code"], row["locked"], _reasons(row["lock_reasons"])
    new_activity = "charging" if row["status"] == "charging" else "idle"

    if not payload.get("offline", False):   # live message — its state is current
        if activity is not KEEP:
            new_activity = activity
        if fault is not KEEP:
            new_fault = fault if fault in BLOCKING_FAULTS else None
        if clear_faults and new_fault in clear_faults:
            new_fault = None
        if lock_reasons is not KEEP and lock_reasons is not None:
            reasons = list(lock_reasons)
            new_locked = bool(reasons)
        if add_reason and add_reason not in reasons:
            reasons.append(add_reason)
            new_locked = True
        if remove_reason and remove_reason in reasons:
            reasons.remove(remove_reason)
            new_locked = bool(reasons)
        if locked is not KEEP and locked is not None:
            new_locked = bool(locked)
            if not new_locked:
                reasons = []

    status = resolve_status(new_activity, new_fault, new_locked)
    await conn.execute(
        """
        UPDATE chargers
        SET    status            = $2::varchar,
               fault_code        = $3,
               locked            = $4,
               lock_reasons      = $5::jsonb,
               status_updated_at = CASE WHEN status IS DISTINCT FROM $2::varchar THEN $6 ELSE status_updated_at END,
               last_seen_at      = $6,
               fw_version        = COALESCE($7, fw_version),
               last_reset_reason = COALESCE($8, last_reset_reason)
        WHERE  charger_id = $1
        """,
        charger_id, status, new_fault, new_locked, json.dumps(reasons),
        datetime.now(timezone.utc), payload.get("fw_version"), reset_reason,
    )
    if status != row["status"]:
        logger.info("Charger status | %s: %s → %s%s", charger_id, row["status"], status,
                    f" ({new_fault or ', '.join(reasons)})" if status in ("fault", "locked") else "")
    return status


async def mark_offline(conn: asyncpg.Connection, charger_id: str) -> None:
    result = await conn.execute(
        """
        UPDATE chargers SET status = 'offline', status_updated_at = $2
        WHERE  charger_id = $1 AND status <> 'offline'
        """,
        charger_id, datetime.now(timezone.utc),
    )
    if result != "UPDATE 0":
        logger.info("Charger status | %s → offline (broker)", charger_id)


async def sweep_silent_chargers(pool: asyncpg.Pool) -> list[str]:
    """Mark chargers offline that have been silent past their limit — mesh nodes never get a broker offline."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            UPDATE chargers
            SET    status = 'offline', status_updated_at = now()
            WHERE  status NOT IN ('offline', 'never_connected')
              AND  last_seen_at < now() - make_interval(mins =>
                       CASE connection_type WHEN 'mesh' THEN $1::int ELSE $2::int END)
            RETURNING charger_id
            """,
            SILENT_LIMIT_MIN["mesh"], SILENT_LIMIT_MIN["hub"],
        )
    ids = [r["charger_id"] for r in rows]
    if ids:
        logger.info("Charger status | silent too long → offline: %s", ", ".join(ids))
    return ids


async def run_silent_sweeper(pool: asyncpg.Pool) -> None:
    """Background loop — runs next to the MQTT subscriber."""
    while True:
        delay = SWEEP_EVERY_S
        try:
            await sweep_silent_chargers(pool)
        except asyncio.CancelledError:
            raise
        except TRANSIENT_DB_ERRORS as e:   # network blip / database waking up — try again soon
            logger.warning("Silent-charger sweep skipped, database unreachable (%s) — retrying in %ss",
                           type(e).__name__, SWEEP_RETRY_S)
            delay = SWEEP_RETRY_S
        except Exception as e:
            logger.exception("Silent-charger sweep failed: %s", e)
        await asyncio.sleep(delay)
