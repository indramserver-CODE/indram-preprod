"""
app/mqtt_commands.py
--------------------
Outbound MQTT commands — server to charger.
Firmware v6.4.0

Topic structure:
  Unicast:   indram/{society_id}/{meter_id}/{charger_id}/cmd/command
  Broadcast: indram/{society_id}/all/cmd/command

Commands:
  DEACTIVATE     — locks one charger, stops active session, persists in EEPROM
  ACTIVE         — re-enables one charger after DEACTIVATE
  DELUID         — removes one RFID UID from one charger's allowlist
  ADDUID         — adds a new RFID UID to one charger's allowlist (max 3 user slots)
  DEACTIVATE_ALL — same as DEACTIVATE applied to every charger in the society (broadcast)
  ACTIVATE_ALL   — same as ACTIVE applied to every charger in the society (broadcast)

Every command payload MUST include:
  token — CMD_AUTH_TOKEN from .env (must match firmware hardcoded value)
  cmd   — command name (case-sensitive)
  ts    — current UTC Unix timestamp generated server-side
          (charger rejects if |charger_time − ts| > 30s — replay attack prevention)

Design principle:
  This module is intentionally stateless — no DB access.
  Callers (routers) already have charger and meter objects in memory and pass
  society_id and meter_id directly. No redundant DB lookup is performed here.

The charger responds on:
  indram/{soc}/{mtr}/{charger_id}/ack/cmd_ack  — result of DEACTIVATE / ACTIVE
  indram/{soc}/{mtr}/{charger_id}/ack/uid_ack  — RFID-specific result of ADDUID
"""

import ssl
import time
import json
import logging

import aiomqtt

from app.config import settings

logger = logging.getLogger(__name__)


def _make_tls_context() -> ssl.SSLContext | None:
    if settings.MQTT_USE_TLS:
        return ssl.create_default_context()
    return None


def _build_payload(cmd: str, extra: dict | None = None) -> bytes:
    """Build a JSON command payload with mandatory auth and timestamp fields."""
    payload = {
        "token": settings.CMD_AUTH_TOKEN,
        "cmd":   cmd,
        "ts":    int(time.time()),   # UTC Unix seconds — always generated server-side
    }
    if extra:
        payload.update(extra)
    return json.dumps(payload).encode("utf-8")


async def _publish(topic: str, cmd: str, extra: dict | None = None):
    """Publish a JSON command to the given topic at QoS 1."""
    payload = _build_payload(cmd, extra)
    tls_ctx = _make_tls_context()

    try:
        async with aiomqtt.Client(
            hostname=settings.MQTT_HOST,
            port=settings.MQTT_PORT,
            username=settings.MQTT_USERNAME or None,
            password=settings.MQTT_PASSWORD or None,
            tls_context=tls_ctx,
        ) as client:
            await client.publish(topic, payload, qos=1)
            logger.info("MQTT command sent | cmd=%s topic=%s", cmd, topic)
    except aiomqtt.MqttError as e:
        logger.error("Failed to publish MQTT command | cmd=%s topic=%s error=%s", cmd, topic, e)
        raise


# ── Unicast commands ────────────────────────────────────────────────────
# Callers pass society_id and meter_id directly — both are already in memory
# on the charger/meter objects fetched by the calling router.

async def send_deactivate(charger_id: str, society_id: int, meter_id: int):
    """
    Lock a single charger.
    Stops any active session (charger fires charging_stopped_by_admin first),
    disables all RFID, persists in EEPROM across power cycles.
    Charger responds with cmd_ack on ack/cmd_ack topic.
    """
    topic = f"indram/{society_id}/{meter_id}/{charger_id}/cmd/command"
    await _publish(topic, "DEACTIVATE")


async def send_active(charger_id: str, society_id: int, meter_id: int):
    """
    Re-enable a single charger after DEACTIVATE.
    Clears the deactivated flag and re-enables all whitelisted RFID UIDs.
    State persists in EEPROM.
    Charger responds with cmd_ack on ack/cmd_ack topic.
    """
    topic = f"indram/{society_id}/{meter_id}/{charger_id}/cmd/command"
    await _publish(topic, "ACTIVE")


async def send_add_uid(charger_id: str, society_id: int, meter_id: int, uid: str):
    """
    Add a new RFID UID to a single charger's local allowlist.
    Max 3 user slots. State persists in EEPROM.
    Charger responds with BOTH uid_ack and cmd_ack on their respective ack topics.
    uid must be uppercase hex with no separators (e.g. "14AF7D05").
    """
    topic = f"indram/{society_id}/{meter_id}/{charger_id}/cmd/command"
    await _publish(topic, "ADDUID", {"uid": uid.upper().strip()})


async def send_del_uid(charger_id: str, society_id: int, meter_id: int, uid: str):
    """
    Remove an RFID UID from a single charger's local allowlist.
    Charger responds with BOTH cmd_ack and uid_ack (uid_removed | uid_remove_failed).
    Never queued — callers must handshake first.
    """
    topic = f"indram/{society_id}/{meter_id}/{charger_id}/cmd/command"
    await _publish(topic, "DELUID", {"uid": uid.upper().strip()})


async def send_handshake(charger_id: str, society_id: int, meter_id: int, request_id: str):
    """
    Send a HANDSHAKE command to a charger.
    Charger echoes request_id back in ack/handshake if online.
    request_id must be unique per request — used to match the ack.
    Never reuse a request_id or send two handshakes in the same second.
    """
    topic = f"indram/{society_id}/{meter_id}/{charger_id}/cmd/handshake"
    await _publish(topic, "HANDSHAKE", {"request_id": request_id})


# ── Broadcast commands ──────────────────────────────────────────────────
# Broadcast uses 'all' as the meter segment — firmware convention.
# Every charger in the society processes this regardless of which meter it belongs to.
# Each charger responds individually with its own cmd_ack.

async def send_deactivate_all(society_id: int):
    """
    Broadcast DEACTIVATE to every charger in a society.
    Topic: indram/{society_id}/all/cmd/command
    Each charger fires charging_stopped_by_admin (if session active) then cmd_ack.
    """
    topic = f"indram/{society_id}/all/cmd/command"
    await _publish(topic, "DEACTIVATE_ALL")
    logger.info("DEACTIVATE_ALL broadcast | society=%s", society_id)


async def send_activate_all(society_id: int):
    """
    Broadcast ACTIVATE to every charger in a society.
    Topic: indram/{society_id}/all/cmd/command
    Re-enables all chargers in the society simultaneously.
    Each charger responds individually with cmd_ack.
    """
    topic = f"indram/{society_id}/all/cmd/command"
    await _publish(topic, "ACTIVATE_ALL")
    logger.info("ACTIVATE_ALL broadcast | society=%s", society_id)