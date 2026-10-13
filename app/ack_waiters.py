"""
app/ack_waiters.py
------------------
In-memory waiter registry for MQTT command acknowledgements and handshakes.

Two separate registries:

1. Command waiters (DEACTIVATE, ACTIVE, ADDUID)
   Key: "{charger_id}:DEACTIVATE" / "{charger_id}:ACTIVE" / "{charger_id}:{uid}:ADDUID"
   Resolved by: handle_cmd_ack, handle_uid_ack in mqtt_subscriber.py

2. Handshake waiters
   Key: request_id (UUID string — unique per handshake request)
   Resolved by: handle_handshake_ack in mqtt_subscriber.py

NOTE: In-memory — works correctly only with a single uvicorn worker.
Replace with Redis pub/sub if you ever scale to multiple workers.
"""

import asyncio
from typing import Any

# ── Command waiters (DEACTIVATE, ACTIVE, ADDUID) ──────────────────────
waiters: dict[str, asyncio.Event]      = {}
results: dict[str, dict[str, Any]]    = {}


def make_key(charger_id: str, cmd: str, uid: str | None = None) -> str:
    if uid:
        return f"{charger_id}:{uid.upper()}:{cmd}"
    return f"{charger_id}:{cmd}"


def register(key: str) -> asyncio.Event:
    """Create and register a command waiter. Returns the event to await on."""
    event = asyncio.Event()
    waiters[key] = event
    results.pop(key, None)
    return event


def resolve(key: str, result: dict[str, Any]):
    """Called by MQTT subscriber. Stores result and wakes up the waiter."""
    results[key] = result
    event = waiters.get(key)
    if event:
        event.set()


def cleanup(key: str):
    """Called after the API route finishes waiting."""
    waiters.pop(key, None)
    results.pop(key, None)


def get_result(key: str) -> dict[str, Any] | None:
    return results.get(key)


# ── Handshake waiters ─────────────────────────────────────────────────
# Keyed on request_id — unique per handshake request so no collision risk
_handshake_waiters: dict[str, asyncio.Event]   = {}
_handshake_results: dict[str, dict[str, Any]]  = {}


def register_handshake(request_id: str) -> asyncio.Event:
    """Register a handshake waiter keyed on request_id."""
    event = asyncio.Event()
    _handshake_waiters[request_id] = event
    _handshake_results.pop(request_id, None)
    return event


def resolve_handshake(request_id: str, payload: dict[str, Any]):
    """Called by MQTT subscriber when handshake_ack arrives."""
    _handshake_results[request_id] = payload
    event = _handshake_waiters.get(request_id)
    if event:
        event.set()


def cleanup_handshake(request_id: str):
    """Called after the API route finishes waiting."""
    _handshake_waiters.pop(request_id, None)
    _handshake_results.pop(request_id, None)


def get_handshake_result(request_id: str) -> dict[str, Any] | None:
    return _handshake_results.get(request_id)