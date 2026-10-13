"""
app/routers/analytics.py
------------------------
Read-only analytics endpoints.

  Society admin sub-router  → registered at /api/analytics/society
  Super admin sub-router    → registered at /api/analytics/admin

────────────────────────────────────────────────────────────────────────
Query strategy — NO new indexes are added.
Every query is designed around the existing index set:

  idx_sessions_charger_id     – charging_sessions(charger_id)
  idx_sessions_started_at     – charging_sessions(started_at)
  idx_sessions_status         – charging_sessions(status)
  idx_sessions_ended_status   – charging_sessions(ended_at, status)  [BR §7]
  idx_sessions_fault_code     – charging_sessions(fault_code) PARTIAL [BR §7]
  idx_flats_society_id        – flats(society_id)                    [BR §7]
  chargers_flat_id_key        – chargers(flat_id)   UNIQUE
  chargers_charger_id_key     – chargers(charger_id) UNIQUE
  charger_status_charger_id_key – charger_status(charger_id) UNIQUE
  idx_flat_bills_flat         – flat_bills(flat_id)
  idx_flat_bills_monthly      – flat_bills(monthly_bill_id)
  monthly_bills_society_id_billing_month_key – UNIQUE

Society-scoped pattern:
  All session aggregations use a small CTE (sc) that resolves the set of
  charger_ids that belong to the society.  The main query then filters with
  "WHERE cs.charger_id IN (SELECT charger_id FROM sc)", which hits
  idx_sessions_charger_id via an index scan for each charger_id.  This keeps
  the expensive charging_sessions table access narrow regardless of total
  session volume on the platform.

Energy calculation:
  units_consumed is nullable/zero on older firmware rows.  We always use
      COALESCE(cs.units_consumed,
               GREATEST(cs.end_meter_kwh - cs.start_meter_kwh, 0.0),
               0.0)
  across all aggregations for consistent figures.
────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import require_society_admin, require_super_admin
from app.models.user import SocietyAdmin, User

logger = logging.getLogger(__name__)

# ── Sub-routers (registered in main.py) ─────────────────────────────────────
router_society = APIRouter()
router_admin   = APIRouter()


@router_admin.get("/ping")
async def admin_ping():
    """Unauthenticated debug endpoint — remove after confirming routing works."""
    return {"status": "ok", "message": "analytics router is alive"}

# ── Shared constants ─────────────────────────────────────────────────────────

# The three terminal statuses that represent completed charging work
ENDED_STATUSES = (
    "charging_ended",
    "charging_ended_error",
    "charging_stopped_by_admin",
)

# A charger is considered offline if its last status MQTT message is older than this
OFFLINE_THRESHOLD_MINUTES = 30

# Fault codes that mean "no fault" — anything else is a real fault
_NOT_A_FAULT = ("0", "", "null", "FC_OK", "none", "None")


# ── Shared helpers ────────────────────────────────────────────────────────────

def _month_bounds(month: str | None) -> tuple[date, date]:
    """
    Return (start_inclusive, end_exclusive) dates for a 'YYYY-MM' string.
    Defaults to the current calendar month if month is None.
    """
    if not month:
        today = date.today()
        month = f"{today.year}-{today.month:02d}"
    try:
        year, mon = map(int, month.split("-"))
        start = date(year, mon, 1)
        end   = date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)
        return start, end
    except (ValueError, AttributeError):
        raise HTTPException(400, "Invalid month format — use YYYY-MM")


async def _get_society_id(user: User, db: AsyncSession) -> int:
    """Resolve the society_id for a society admin.  403 if not assigned."""
    result = await db.execute(
        select(SocietyAdmin.society_id).where(SocietyAdmin.user_id == user.id)
    )
    sid = result.scalar_one_or_none()
    if not sid:
        raise HTTPException(403, "No society assigned to this admin")
    return sid


def _safe_float(v) -> float | None:
    """Convert a Decimal / numeric DB value to float, returning None if null."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _safe_float_zero(v) -> float:
    """Like _safe_float but returns 0.0 instead of None."""
    return _safe_float(v) or 0.0


# ═════════════════════════════════════════════════════════════════════════════
#  SOCIETY ADMIN ENDPOINTS
# ═════════════════════════════════════════════════════════════════════════════

# ── 1. Daily Energy ──────────────────────────────────────────────────────────

class DailyEnergyRow(BaseModel):
    date: str           # "2026-05-01"
    kwh: float
    fault_sessions: int
    total_sessions: int


@router_society.get("/daily-energy", response_model=list[DailyEnergyRow])
async def daily_energy(
    month: str | None = Query(None, description="YYYY-MM, defaults to current month"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_society_admin),
):
    """
    kWh consumed + fault session count per calendar day for the requested month.

    Index path:
      sc CTE  → chargers(flat_id) UNIQUE + flats(society_id) via idx_flats_society_id
      main    → idx_sessions_charger_id (IN lookup) + idx_sessions_ended_status (date/status)
    """
    sid         = await _get_society_id(user, db)
    start, end  = _month_bounds(month)

    sql = text("""
        WITH sc AS (
            SELECT c.charger_id
              FROM chargers  c
              JOIN flats     f ON f.id = c.flat_id
             WHERE f.society_id = :sid
        )
        SELECT
            DATE(cs.ended_at)::text                                       AS date,
            COALESCE(SUM(
                COALESCE(cs.units_consumed,
                         GREATEST(cs.end_meter_kwh - cs.start_meter_kwh, 0.0),
                         0.0)
            ), 0)::float                                                  AS kwh,
            COUNT(*) FILTER (
                WHERE cs.status = 'charging_ended_error'
            )::int                                                        AS fault_sessions,
            COUNT(*)::int                                                 AS total_sessions
          FROM charging_sessions cs
         WHERE cs.charger_id  IN (SELECT charger_id FROM sc)
           AND cs.status       = ANY(:statuses)
           AND cs.ended_at    >= :start
           AND cs.ended_at     < :end
         GROUP BY DATE(cs.ended_at)
         ORDER BY date
    """)
    rows = (
        await db.execute(
            sql,
            {"sid": sid, "statuses": list(ENDED_STATUSES), "start": start, "end": end},
        )
    ).all()

    return [
        DailyEnergyRow(
            date=r.date,
            kwh=r.kwh,
            fault_sessions=r.fault_sessions,
            total_sessions=r.total_sessions,
        )
        for r in rows
    ]


# ── 2. Peak Hours Heatmap ────────────────────────────────────────────────────

class PeakHourRow(BaseModel):
    dow: int    # 0 = Sunday … 6 = Saturday (PostgreSQL EXTRACT(DOW))
    hour: int   # 0 – 23
    count: int


@router_society.get("/peak-hours", response_model=list[PeakHourRow])
async def peak_hours(
    month: str | None = Query(None, description="YYYY-MM, defaults to current month"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_society_admin),
):
    """
    7×24 session count matrix (day-of-week × hour).  Used to draw the heatmap.

    Index path:
      sc CTE  → chargers + flats as above
      main    → idx_sessions_charger_id + idx_sessions_started_at (date range)
    Only rows that actually have counts are returned; the frontend fills zeros.
    """
    sid        = await _get_society_id(user, db)
    start, end = _month_bounds(month)

    sql = text("""
        WITH sc AS (
            SELECT c.charger_id
              FROM chargers c
              JOIN flats    f ON f.id = c.flat_id
             WHERE f.society_id = :sid
        )
        SELECT
            EXTRACT(DOW  FROM cs.started_at)::int  AS dow,
            EXTRACT(HOUR FROM cs.started_at)::int  AS hour,
            COUNT(*)::int                           AS count
          FROM charging_sessions cs
         WHERE cs.charger_id  IN (SELECT charger_id FROM sc)
           AND cs.started_at >= :start
           AND cs.started_at  < :end
         GROUP BY EXTRACT(DOW FROM cs.started_at),
                  EXTRACT(HOUR FROM cs.started_at)
         ORDER BY dow, hour
    """)
    # Note: we do NOT filter on status here — we want to see ALL session starts
    # (active, ended, error) so the heatmap reflects true usage peaks.
    rows = (
        await db.execute(sql, {"sid": sid, "start": start, "end": end})
    ).all()

    return [PeakHourRow(dow=r.dow, hour=r.hour, count=r.count) for r in rows]


# ── 3. Charger Health ────────────────────────────────────────────────────────

class ChargerHealthRow(BaseModel):
    charger_id:     str
    flat_number:    str | None
    charger_status: str | None      # may be overridden to "fault" or "offline"
    voltage:        float | None
    current:        float | None
    energy_kwh:     float | None
    temperature_c:  float | None
    duration_min:   int | None
    fault_code:     str | None
    last_seen_at:   str | None      # ISO-8601
    fw_version:     str | None
    is_active:      bool


@router_society.get("/charger-health", response_model=list[ChargerHealthRow])
async def charger_health(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_society_admin),
):
    """
    Live status for all chargers in the society.
    LEFT JOIN on charger_status so offline (never-connected) chargers still appear.
    Status is overridden on the backend:
      • "fault"   if fault_code is set and not a known no-fault code
      • "offline" if last MQTT status is > OFFLINE_THRESHOLD_MINUTES old
    No date filter — always current.

    Index path:
      chargers → flats join via chargers_flat_id_key UNIQUE
      flats    → idx_flats_society_id
      cs_status → charger_status_charger_id_key UNIQUE (LEFT JOIN)
    """
    sid = await _get_society_id(user, db)

    sql = text("""
        SELECT
            c.charger_id,
            f.flat_number,
            cs.charger_status,
            cs.voltage::float,
            cs.current::float,
            cs.energy_kwh::float,
            cs.temperature_c::float,
            cs.duration_min,
            cs.fault_code,
            cs.received_at,
            c.fw_version,
            c.is_active
          FROM chargers       c
          JOIN flats          f  ON f.id         = c.flat_id
          LEFT JOIN charger_status cs ON cs.charger_id = c.charger_id
         WHERE f.society_id = :sid
         ORDER BY c.charger_id
    """)
    rows = (await db.execute(sql, {"sid": sid})).all()

    result = []
    threshold = datetime.now(timezone.utc).replace(
        second=0, microsecond=0
    )
    for r in rows:
        status    = r.charger_status
        fault     = r.fault_code
        last_seen = r.received_at

        # Override status with "fault" if a real fault code is present
        if fault and fault not in _NOT_A_FAULT:
            status = "fault"
        # Override with "offline" if last heartbeat is too old (or never)
        elif last_seen is None or (
            datetime.now(timezone.utc) - last_seen
        ).total_seconds() > OFFLINE_THRESHOLD_MINUTES * 60:
            status = "offline"

        result.append(
            ChargerHealthRow(
                charger_id=r.charger_id,
                flat_number=r.flat_number,
                charger_status=status,
                voltage=r.voltage,
                current=r.current,
                energy_kwh=r.energy_kwh,
                temperature_c=r.temperature_c,
                duration_min=r.duration_min,
                fault_code=fault,
                last_seen_at=last_seen.isoformat() if last_seen else None,
                fw_version=r.fw_version,
                is_active=r.is_active,
            )
        )
    return result


# ── 4. Fault Analysis ────────────────────────────────────────────────────────

class FaultSummaryItem(BaseModel):
    fault_code:        str
    count:             int
    avg_temp_c:        float | None
    chargers_affected: list[str]


class FaultAnalysisOut(BaseModel):
    fault_summary:       list[FaultSummaryItem]
    top_offender_charger: str | None
    avg_temp_at_fault:   float | None


@router_society.get("/fault-analysis", response_model=FaultAnalysisOut)
async def fault_analysis(
    months: int = Query(3, ge=1, le=24, description="Look-back window in months"),
    db: AsyncSession  = Depends(get_db),
    user: User        = Depends(require_society_admin),
):
    """
    Fault code frequency + average temperature at fault time.
    Look-back window controlled by `months` parameter (default 3).

    Index path:
      sc CTE     → chargers + flats
      main query → idx_sessions_charger_id + idx_sessions_fault_code (partial)
      The partial index covers fault_code IS NOT NULL rows only, making this
      very fast even as session volume grows.
    """
    sid = await _get_society_id(user, db)

    sql = text("""
        WITH sc AS (
            SELECT c.charger_id
              FROM chargers c
              JOIN flats    f ON f.id = c.flat_id
             WHERE f.society_id = :sid
        )
        SELECT
            cs.fault_code,
            COUNT(*)::int                       AS count,
            AVG(cs.temperature_c)::float        AS avg_temp_c,
            ARRAY_AGG(DISTINCT cs.charger_id)   AS chargers_affected
          FROM charging_sessions cs
         WHERE cs.charger_id IN (SELECT charger_id FROM sc)
           AND cs.fault_code IS NOT NULL
           AND cs.fault_code NOT IN ('0', '', 'null', 'FC_OK', 'none', 'None')
           AND cs.ended_at  >= NOW() - (:months * INTERVAL '1 month')
         GROUP BY cs.fault_code
         ORDER BY count DESC
    """)

    rows = (await db.execute(sql, {"sid": sid, "months": months})).all()
    if not rows:
        return FaultAnalysisOut(
            fault_summary=[], top_offender_charger=None, avg_temp_at_fault=None
        )

    fault_summary = [
        FaultSummaryItem(
            fault_code=r.fault_code,
            count=r.count,
            avg_temp_c=_safe_float(r.avg_temp_c),
            chargers_affected=list(r.chargers_affected or []),
        )
        for r in rows
    ]

    # top_offender = charger with most fault sessions overall
    top_sql = text("""
        WITH sc AS (
            SELECT c.charger_id
              FROM chargers c
              JOIN flats    f ON f.id = c.flat_id
             WHERE f.society_id = :sid
        )
        SELECT cs.charger_id, COUNT(*) AS n
          FROM charging_sessions cs
         WHERE cs.charger_id IN (SELECT charger_id FROM sc)
           AND cs.fault_code IS NOT NULL
           AND cs.fault_code NOT IN ('0', '', 'null', 'FC_OK', 'none', 'None')
           AND cs.ended_at  >= NOW() - (:months * INTERVAL '1 month')
         GROUP BY cs.charger_id
         ORDER BY n DESC
         LIMIT 1
    """)
    top_row = (await db.execute(top_sql, {"sid": sid, "months": months})).first()

    # overall avg temperature across all fault sessions
    avg_temp_at_fault = (
        sum(
            r.avg_temp_c * r.count
            for r in rows
            if r.avg_temp_c is not None
        ) / sum(r.count for r in rows if r.avg_temp_c is not None)
        if any(r.avg_temp_c is not None for r in rows)
        else None
    )

    return FaultAnalysisOut(
        fault_summary=fault_summary,
        top_offender_charger=top_row.charger_id if top_row else None,
        avg_temp_at_fault=avg_temp_at_fault,
    )


# ── 5. Session Duration Distribution ────────────────────────────────────────

class SessionDurationRow(BaseModel):
    bucket_label: str
    count: int


@router_society.get("/session-duration", response_model=list[SessionDurationRow])
async def session_duration(
    month: str | None = Query(None, description="YYYY-MM, defaults to current month"),
    db: AsyncSession  = Depends(get_db),
    user: User        = Depends(require_society_admin),
):
    """
    Histogram of session durations across 5 buckets.
    Only sessions with both started_at and ended_at are included.

    Index path: sc CTE + idx_sessions_charger_id + idx_sessions_ended_status
    """
    sid        = await _get_society_id(user, db)
    start, end = _month_bounds(month)

    sql = text("""
        WITH sc AS (
            SELECT c.charger_id
              FROM chargers c
              JOIN flats    f ON f.id = c.flat_id
             WHERE f.society_id = :sid
        ),
        durations AS (
            SELECT
                EXTRACT(EPOCH FROM (cs.ended_at - cs.started_at)) / 60.0 AS dur_min
              FROM charging_sessions cs
             WHERE cs.charger_id IN (SELECT charger_id FROM sc)
               AND cs.status      = ANY(:statuses)
               AND cs.ended_at   >= :start
               AND cs.ended_at    < :end
               AND cs.ended_at    IS NOT NULL
               AND cs.started_at  IS NOT NULL
        )
        SELECT
            CASE
                WHEN dur_min <  30  THEN 1
                WHEN dur_min <  60  THEN 2
                WHEN dur_min < 120  THEN 3
                WHEN dur_min < 240  THEN 4
                ELSE                     5
            END                    AS sort_key,
            CASE
                WHEN dur_min <  30  THEN '0–30 min'
                WHEN dur_min <  60  THEN '30–60 min'
                WHEN dur_min < 120  THEN '1–2 hrs'
                WHEN dur_min < 240  THEN '2–4 hrs'
                ELSE                     '4+ hrs'
            END                    AS bucket_label,
            COUNT(*)::int          AS count
          FROM durations
         GROUP BY sort_key, bucket_label
         ORDER BY sort_key
    """)
    rows = (
        await db.execute(
            sql,
            {"sid": sid, "statuses": list(ENDED_STATUSES), "start": start, "end": end},
        )
    ).all()

    # Always return all 5 buckets (some may have count=0)
    bucket_order = ["0–30 min", "30–60 min", "1–2 hrs", "2–4 hrs", "4+ hrs"]
    counts = {r.bucket_label: r.count for r in rows}
    return [
        SessionDurationRow(bucket_label=b, count=counts.get(b, 0))
        for b in bucket_order
    ]


# ── 6. RFID Usage Summary ────────────────────────────────────────────────────

class RfidUsageRow(BaseModel):
    rfid_uid:    str
    flat_number: str | None
    sessions:    int
    total_kwh:   float


@router_society.get("/rfid-usage", response_model=list[RfidUsageRow])
async def rfid_usage(
    month: str | None = Query(None, description="YYYY-MM, defaults to current month"),
    db: AsyncSession  = Depends(get_db),
    user: User        = Depends(require_society_admin),
):
    """
    Usage grouped by RFID card UID, joined to flat via rfid_cards table.
    LEFT JOIN so unregistered card UIDs (not yet in rfid_cards) still appear.

    Index path:
      sc CTE + idx_sessions_charger_id + idx_sessions_ended_status
      rfid_cards.uid UNIQUE index on the LEFT JOIN
    """
    sid        = await _get_society_id(user, db)
    start, end = _month_bounds(month)

    sql = text("""
        WITH sc AS (
            SELECT c.charger_id
              FROM chargers c
              JOIN flats    f ON f.id = c.flat_id
             WHERE f.society_id = :sid
        )
        SELECT
            cs.rfid_uid,
            f.flat_number,
            COUNT(*)::int                                           AS sessions,
            COALESCE(SUM(
                COALESCE(cs.units_consumed,
                         GREATEST(cs.end_meter_kwh - cs.start_meter_kwh, 0.0),
                         0.0)
            ), 0)::float                                           AS total_kwh
          FROM charging_sessions cs
          LEFT JOIN rfid_cards rc ON rc.uid   = cs.rfid_uid
          LEFT JOIN flats      f  ON f.id     = rc.flat_id
         WHERE cs.charger_id IN (SELECT charger_id FROM sc)
           AND cs.rfid_uid    IS NOT NULL
           AND cs.status       = ANY(:statuses)
           AND cs.ended_at    >= :start
           AND cs.ended_at     < :end
         GROUP BY cs.rfid_uid, f.flat_number
         ORDER BY sessions DESC
    """)
    rows = (
        await db.execute(
            sql,
            {"sid": sid, "statuses": list(ENDED_STATUSES), "start": start, "end": end},
        )
    ).all()

    return [
        RfidUsageRow(
            rfid_uid=r.rfid_uid,
            flat_number=r.flat_number,
            sessions=r.sessions,
            total_kwh=r.total_kwh,
        )
        for r in rows
    ]


# ── 7. Billing Trend ─────────────────────────────────────────────────────────

class BillingTrendRow(BaseModel):
    month:                str       # "2026-05"
    total_bill_amount:    float
    total_units_consumed: float
    effective_unit_rate:  float
    indram_charges_total: float     # SUM of flat_bills.indram_charges
    emails_sent:          int       # COUNT of flat_bills WHERE email_status='sent'
    emails_failed:        int       # COUNT of flat_bills WHERE email_status='failed'


@router_society.get("/billing-trend", response_model=list[BillingTrendRow])
async def billing_trend(
    months: int = Query(6, ge=1, le=24, description="Number of past months to return"),
    db: AsyncSession  = Depends(get_db),
    user: User        = Depends(require_society_admin),
):
    """
    Monthly billing summary for the last N months.

    Note: monthly_bills does not store indram_charges_total or email counts.
    These are aggregated from flat_bills (LEFT JOIN to handle months where
    some flats were skipped in billing).

    Index path:
      monthly_bills → monthly_bills_society_id_billing_month_key (UNIQUE)
      flat_bills    → idx_flat_bills_monthly (on monthly_bill_id)
    """
    sid = await _get_society_id(user, db)

    sql = text("""
        SELECT
            TO_CHAR(mb.billing_month, 'YYYY-MM')              AS month,
            mb.total_bill_amount::float,
            mb.total_units_consumed::float,
            mb.effective_unit_rate::float,
            COALESCE(SUM(fb.indram_charges), 0)::float        AS indram_charges_total,
            COUNT(*) FILTER (
                WHERE fb.email_status = 'sent'
            )::int                                            AS emails_sent,
            COUNT(*) FILTER (
                WHERE fb.email_status = 'failed'
            )::int                                            AS emails_failed
          FROM monthly_bills mb
          JOIN meters m ON m.id = mb.meter_id
          LEFT JOIN flat_bills fb ON fb.monthly_bill_id = mb.id
         WHERE m.society_id = :sid
           AND mb.status = 'sent'
         GROUP BY mb.id, mb.billing_month,
                  mb.total_bill_amount,
                  mb.total_units_consumed,
                  mb.effective_unit_rate
         ORDER BY mb.billing_month DESC
         LIMIT :months
    """)
    rows = (await db.execute(sql, {"sid": sid, "months": months})).all()

    return [
        BillingTrendRow(
            month=r.month,
            total_bill_amount=r.total_bill_amount,
            total_units_consumed=r.total_units_consumed,
            effective_unit_rate=r.effective_unit_rate,
            indram_charges_total=r.indram_charges_total,
            emails_sent=r.emails_sent,
            emails_failed=r.emails_failed,
        )
        for r in rows
    ]


# ── 8. Download Report ───────────────────────────────────────────────────────

class DownloadReportRequest(BaseModel):
    format:     str                     # "csv" | "excel" | "pdf"
    month:      str                     # "YYYY-MM"
    society_id: int | None = None       # None = platform-wide; int = filter to one society
    sections:   list[str] = [           # which sheets/sections to include
        "energy", "sessions", "billing", "faults", "chargers"
    ]


@router_society.post("/download-report")
async def download_report(
    req: DownloadReportRequest,
    db: AsyncSession = Depends(get_db),
    user: User       = Depends(require_society_admin),
):
    """
    Generate a downloadable analytics report for the selected month.
    Supported formats: csv (single sheet — daily energy), excel (multi-sheet), pdf.
    """
    sid        = await _get_society_id(user, db)
    start, end = _month_bounds(req.month)
    fmt        = req.format.lower()

    if fmt not in ("csv", "excel", "pdf"):
        raise HTTPException(400, "format must be csv, excel, or pdf")

    # ── Gather data ───────────────────────────────────────────────────────
    data: dict = {}

    if "energy" in req.sections or fmt == "csv":
        energy_sql = text("""
            WITH sc AS (
                SELECT c.charger_id FROM chargers c
                JOIN flats f ON f.id = c.flat_id WHERE f.society_id = :sid
            )
            SELECT
                DATE(cs.ended_at)::text AS date,
                COALESCE(SUM(COALESCE(cs.units_consumed,
                    GREATEST(cs.end_meter_kwh - cs.start_meter_kwh, 0.0), 0.0)), 0)::float AS kwh,
                COUNT(*) FILTER (WHERE cs.status = 'charging_ended_error')::int AS fault_sessions,
                COUNT(*)::int AS total_sessions
              FROM charging_sessions cs
             WHERE cs.charger_id IN (SELECT charger_id FROM sc)
               AND cs.status = ANY(:statuses)
               AND cs.ended_at >= :start AND cs.ended_at < :end
             GROUP BY DATE(cs.ended_at) ORDER BY date
        """)
        data["energy"] = (await db.execute(
            energy_sql,
            {"sid": sid, "statuses": list(ENDED_STATUSES), "start": start, "end": end},
        )).all()

    if "faults" in req.sections and fmt != "csv":
        faults_sql = text("""
            WITH sc AS (
                SELECT c.charger_id FROM chargers c
                JOIN flats f ON f.id = c.flat_id WHERE f.society_id = :sid
            )
            SELECT cs.fault_code,
                   COUNT(*)::int AS count,
                   AVG(cs.temperature_c)::float AS avg_temp_c,
                   ARRAY_AGG(DISTINCT cs.charger_id) AS chargers_affected
              FROM charging_sessions cs
             WHERE cs.charger_id IN (SELECT charger_id FROM sc)
               AND cs.fault_code IS NOT NULL
               AND cs.fault_code NOT IN ('0', '', 'null', 'FC_OK', 'none', 'None')
               AND cs.ended_at >= :start AND cs.ended_at < :end
             GROUP BY cs.fault_code ORDER BY count DESC
        """)
        data["faults"] = (await db.execute(
            faults_sql, {"sid": sid, "start": start, "end": end}
        )).all()


    if "billing" in req.sections and fmt != "csv":
        billing_sql = text("""
            SELECT TO_CHAR(mb.billing_month, 'YYYY-MM') AS month,
                   mb.total_bill_amount::float,
                   mb.total_units_consumed::float,
                   mb.effective_unit_rate::float,
                   COALESCE(SUM(fb.indram_charges), 0)::float AS indram_charges_total
              FROM monthly_bills mb
              JOIN meters m ON m.id = mb.meter_id
              LEFT JOIN flat_bills fb ON fb.monthly_bill_id = mb.id
             WHERE m.society_id = :sid
               AND mb.status = 'sent'
             GROUP BY mb.id, mb.billing_month, mb.total_bill_amount,
                      mb.total_units_consumed, mb.effective_unit_rate
             ORDER BY mb.billing_month DESC LIMIT 12
        """)
        data["billing"] = (await db.execute(billing_sql, {"sid": sid})).all()

    if "chargers" in req.sections and fmt != "csv":
        chargers_sql = text("""
            SELECT c.charger_id, f.flat_number,
                   cs.charger_status, cs.voltage::float, cs.current::float,
                   cs.temperature_c::float, cs.fault_code,
                   cs.received_at, c.fw_version, c.is_active
              FROM chargers c
              JOIN flats f ON f.id = c.flat_id
              LEFT JOIN charger_status cs ON cs.charger_id = c.charger_id
             WHERE f.society_id = :sid ORDER BY c.charger_id
        """)
        data["chargers"] = (await db.execute(chargers_sql, {"sid": sid})).all()

    # ── Render ────────────────────────────────────────────────────────────
    filename_base = f"indram-report-{req.month}"

    if fmt == "csv":
        return _render_csv(data, filename_base)
    elif fmt == "excel":
        return _render_excel(data, filename_base, req.month)
    else:  # pdf
        return _render_pdf(data, filename_base, req.month)


def _render_csv(data: dict, filename_base: str) -> StreamingResponse:
    """CSV export — daily energy sheet (most commonly shared externally)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Date", "kWh", "Total Sessions", "Fault Sessions"])
    for r in data.get("energy", []):
        writer.writerow([r.date, round(r.kwh, 3), r.total_sessions, r.fault_sessions])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename_base}.csv"'},
    )


def _render_excel(data: dict, filename_base: str, month: str) -> StreamingResponse:
    """
    Multi-sheet Excel workbook.
    openpyxl is already in requirements.txt.
    """
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        raise HTTPException(500, "openpyxl not installed — run: pip install openpyxl")

    HEADER_FILL = PatternFill("solid", fgColor="0F2B4C")
    HEADER_FONT = Font(bold=True, color="FFFFFF", name="Calibri")

    def _write_sheet(ws, headers: list[str], rows, row_extractor):
        ws.append(headers)
        for cell in ws[1]:
            cell.font = HEADER_FILL and HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = Alignment(horizontal="center")
        for r in rows:
            ws.append(row_extractor(r))
        # Auto-width (rough estimate)
        for col in ws.columns:
            max_len = max((len(str(c.value or "")) for c in col), default=10)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 40)

    wb = openpyxl.Workbook()

    # Sheet 1: Daily Energy
    ws1 = wb.active
    ws1.title = "Daily Energy"
    _write_sheet(
        ws1,
        ["Date", "kWh", "Total Sessions", "Fault Sessions"],
        data.get("energy", []),
        lambda r: [r.date, round(r.kwh, 3), r.total_sessions, r.fault_sessions],
    )

    # Sheet 2: Fault Analysis
    if "faults" in data:
        ws2 = wb.create_sheet("Fault Analysis")
        _write_sheet(
            ws2,
            ["Fault Code", "Count", "Avg Temp at Fault (°C)", "Chargers Affected"],
            data["faults"],
            lambda r: [
                r.fault_code,
                r.count,
                round(r.avg_temp_c, 1) if r.avg_temp_c else "",
                ", ".join(r.chargers_affected or []),
            ],
        )


    # Sheet 3: Billing Summary
    if "billing" in data:
        ws3 = wb.create_sheet("Billing Summary")
        _write_sheet(
            ws3,
            ["Month", "Total Bill (Rs.)", "Units (kWh)", "Unit Rate", "Indram Revenue (Rs.)"],
            data["billing"],
            lambda r: [
                r.month,
                round(r.total_bill_amount, 2),
                round(r.total_units_consumed, 3),
                round(r.effective_unit_rate, 4),
                round(r.indram_charges_total, 2),
            ],
        )

    # Sheet 4: Charger Health
    if "chargers" in data:
        ws4 = wb.create_sheet("Charger Health")
        _write_sheet(
            ws4,
            [
                "Charger ID", "Flat", "Status", "Voltage (V)",
                "Current (A)", "Temp (°C)", "Fault Code", "FW Version",
                "Last Seen", "Active",
            ],
            data["chargers"],
            lambda r: [
                r.charger_id,
                r.flat_number or "",
                r.charger_status or "",
                round(r.voltage, 2) if r.voltage else "",
                round(r.current, 2) if r.current else "",
                round(r.temperature_c, 1) if r.temperature_c else "",
                r.fault_code or "",
                r.fw_version or "",
                r.received_at.strftime("%Y-%m-%d %H:%M") if r.received_at else "Never",
                "Yes" if r.is_active else "No",
            ],
        )

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.read()]),
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": f'attachment; filename="{filename_base}.xlsx"'
        },
    )


def _render_pdf(data: dict, filename_base: str, month: str) -> StreamingResponse:
    """
    Simple tabular PDF report using ReportLab (already in requirements.txt).
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
        )
    except ImportError:
        raise HTTPException(500, "reportlab not installed")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                             leftMargin=2*cm, rightMargin=2*cm,
                             topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story  = []

    NAVY   = colors.HexColor("#0F2B4C")
    LIGHT  = colors.HexColor("#EBF0F7")

    def _section_heading(title: str):
        story.append(Spacer(1, 0.4*cm))
        story.append(Paragraph(f"<b><font color='#0F2B4C'>{title}</font></b>",
                                styles["Heading2"]))
        story.append(Spacer(1, 0.2*cm))

    def _make_table(headers, rows_data):
        t_data   = [headers] + rows_data
        col_w    = [(A4[0] - 4*cm) / len(headers)] * len(headers)
        tbl      = Table(t_data, colWidths=col_w, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",   (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#C5CDD9")),
            ("LEFTPADDING",  (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING",   (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
        ]))
        return tbl

    # Title
    story.append(Paragraph(
        f"<b>INDRAM EV Charging — Analytics Report</b>",
        styles["Title"],
    ))
    story.append(Paragraph(
        f"Month: {month} &nbsp;|&nbsp; Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} IST",
        styles["Normal"],
    ))
    story.append(Spacer(1, 0.4*cm))

    # Daily Energy table
    if "energy" in data and data["energy"]:
        _section_heading("Daily Energy Consumption")
        rows_data = [
            [r.date, f"{r.kwh:.3f}", str(r.total_sessions), str(r.fault_sessions)]
            for r in data["energy"]
        ]
        story.append(_make_table(
            ["Date", "kWh", "Sessions", "Fault Sessions"],
            rows_data,
        ))

    # Fault Analysis table
    if "faults" in data and data["faults"]:
        _section_heading("Fault Analysis")
        rows_data = [
            [
                r.fault_code,
                str(r.count),
                f"{r.avg_temp_c:.1f}" if r.avg_temp_c else "—",
                ", ".join(r.chargers_affected or []),
            ]
            for r in data["faults"]
        ]
        story.append(_make_table(
            ["Fault Code", "Count", "Avg Temp (°C)", "Chargers Affected"],
            rows_data,
        ))


    # Billing Summary table
    if "billing" in data and data["billing"]:
        _section_heading("Billing Summary")
        rows_data = [
            [
                r.month,
                f"Rs.{r.total_bill_amount:,.2f}",
                f"{r.total_units_consumed:.2f}",
                f"Rs.{r.effective_unit_rate:.4f}",
                f"Rs.{r.indram_charges_total:,.2f}",
            ]
            for r in data["billing"]
        ]
        story.append(_make_table(
            ["Month", "Total Bill (Rs.)", "Units (kWh)", "Unit Rate", "Indram Rev (Rs.)"],
            rows_data,
        ))

    doc.build(story)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.read()]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename_base}.pdf"'
        },
    )


# ═════════════════════════════════════════════════════════════════════════════
#  SUPER ADMIN ENDPOINTS
# ═════════════════════════════════════════════════════════════════════════════

# ── 1. Platform Overview ─────────────────────────────────────────────────────

class OverviewOut(BaseModel):
    total_societies:          int
    total_chargers:           int
    total_flats:              int
    active_sessions:          int
    platform_kwh_month:       float
    platform_sessions_month:  int
    indram_revenue_month:     float
    chargers_online:          int
    chargers_offline:         int
    fleet_availability_pct:   float
    fault_rate_pct:           float
    latest_fw_version:        str | None
    chargers_on_latest_fw:    int
    chargers_outdated_fw:     int


@router_admin.get("/overview", response_model=OverviewOut)
async def platform_overview(
    society_id: int | None = Query(None, description="Filter to one society"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    """
    Platform-wide KPI snapshot.

    The society filter is injected directly into the SQL string (safe — it is
    either None or a validated integer from FastAPI Query, never raw user text).
    This avoids the brittle :sid_filter::int = -1 OR ... pattern that fails on
    some asyncpg/SQLAlchemy versions.
    """
    import traceback

    today       = date.today()
    month_start = date(today.year, today.month, 1)
    month_end   = (
        date(today.year + 1, 1, 1)
        if today.month == 12
        else date(today.year, today.month + 1, 1)
    )

    # society_id is a validated int|None from FastAPI — safe to interpolate
    if society_id:
        sw   = f"_f.society_id = {int(society_id)}"   # charger/session CTEs
        sw_b = f"m.society_id = {int(society_id)}"    # billing CTE (joins through meters)
        sw_c = f"_f.society_id = {int(society_id)}"   # fw count subqueries
        sw_t = f"f2.society_id = {int(society_id)}"   # totals charger count
        sw_f = f"f3.society_id = {int(society_id)}"   # totals flat count
    else:
        sw = sw_b = sw_c = sw_t = sw_f = "TRUE"

    sql = text(f"""
        WITH totals AS (
            SELECT
                (SELECT COUNT(*) FROM societies)::int AS total_societies,
                (
                    SELECT COUNT(*) FROM chargers c2
                    JOIN flats f2 ON f2.id = c2.flat_id
                    WHERE {sw_t}
                )::int AS total_chargers,
                (
                    SELECT COUNT(*) FROM flats f3
                    WHERE {sw_f}
                )::int AS total_flats
        ),

        session_stats AS (
            SELECT
                COALESCE(COUNT(*) FILTER (
                    WHERE cs.status NOT IN (
                        'charging_ended','charging_ended_error','charging_stopped_by_admin'
                    )
                ), 0)::int AS active_sessions,

                COALESCE(SUM(
                    COALESCE(cs.units_consumed,
                        GREATEST(COALESCE(cs.end_meter_kwh,0) - COALESCE(cs.start_meter_kwh,0), 0.0),
                        0.0)
                ) FILTER (
                    WHERE cs.status IN ('charging_ended','charging_ended_error','charging_stopped_by_admin')
                    AND cs.ended_at >= :month_start AND cs.ended_at < :month_end
                ), 0)::float AS platform_kwh_month,

                COALESCE(COUNT(*) FILTER (
                    WHERE cs.status IN ('charging_ended','charging_ended_error','charging_stopped_by_admin')
                    AND cs.ended_at >= :month_start AND cs.ended_at < :month_end
                ), 0)::int AS platform_sessions_month,

                COALESCE(COUNT(*) FILTER (
                    WHERE cs.status = 'charging_ended_error'
                    AND cs.ended_at >= :month_start AND cs.ended_at < :month_end
                ), 0)::int AS fault_sessions_month

            FROM chargers _c
            JOIN flats _f ON _f.id = _c.flat_id
            LEFT JOIN charging_sessions cs ON cs.charger_id = _c.charger_id
            WHERE {sw}
        ),

        billing_stats AS (
            SELECT COALESCE(SUM(fb.indram_charges), 0)::float AS indram_revenue_month
            FROM flat_bills fb
            JOIN monthly_bills mb ON mb.id = fb.monthly_bill_id
            JOIN meters m ON m.id = mb.meter_id
            WHERE mb.billing_month >= :month_start
              AND mb.billing_month  < :month_end
              AND mb.status = 'sent'
              AND {sw_b}
        ),

        charger_avail AS (
            SELECT
                COALESCE(COUNT(*) FILTER (
                    WHERE cst.received_at > NOW() - INTERVAL '30 minutes'
                ), 0)::int AS chargers_online,
                COUNT(*)::int AS total
            FROM chargers c
            JOIN flats _f ON _f.id = c.flat_id
            LEFT JOIN charger_status cst ON cst.charger_id = c.charger_id
            WHERE {sw}
        ),

        fw_stats AS (
            SELECT (
                SELECT c.fw_version
                FROM chargers c
                JOIN flats _f ON _f.id = c.flat_id
                WHERE c.fw_version IS NOT NULL AND {sw}
                GROUP BY c.fw_version
                ORDER BY COUNT(*) DESC
                LIMIT 1
            ) AS latest_fw_version
        )

        SELECT
            t.total_societies, t.total_chargers, t.total_flats,
            ss.active_sessions, ss.platform_kwh_month, ss.platform_sessions_month,
            bs.indram_revenue_month,
            ca.chargers_online,
            (ca.total - ca.chargers_online) AS chargers_offline,
            CASE WHEN ca.total > 0
                 THEN ROUND((ca.chargers_online::numeric / ca.total) * 100, 1)::float
                 ELSE 0::float END AS fleet_availability_pct,
            CASE WHEN ss.platform_sessions_month > 0
                 THEN ROUND((ss.fault_sessions_month::numeric / ss.platform_sessions_month) * 100, 1)::float
                 ELSE 0::float END AS fault_rate_pct,
            fw.latest_fw_version,
            COALESCE((
                SELECT COUNT(*)::int FROM chargers c JOIN flats _f ON _f.id = c.flat_id
                WHERE c.fw_version = fw.latest_fw_version AND {sw_c}
            ), 0) AS chargers_on_latest_fw,
            (t.total_chargers - COALESCE((
                SELECT COUNT(*)::int FROM chargers c JOIN flats _f ON _f.id = c.flat_id
                WHERE c.fw_version = fw.latest_fw_version AND {sw_c}
            ), 0)) AS chargers_outdated_fw
        FROM totals t, session_stats ss, billing_stats bs, charger_avail ca, fw_stats fw
    """)

    params = {"month_start": month_start, "month_end": month_end}

    try:
        logger.info("EXECUTING OVERVIEW QUERY (society_id=%s)", society_id)
        row = (await db.execute(sql, params)).first()
        logger.info("OVERVIEW QUERY OK")
    except Exception as e:
        traceback.print_exc()
        logger.error("Overview query failed: %s", str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to compute analytics overview: {e}",
        )

    if not row:
        raise HTTPException(
            status_code=500,
            detail="No analytics overview data returned",
        )

    return OverviewOut(
        total_societies=row.total_societies or 0,
        total_chargers=row.total_chargers or 0,
        total_flats=row.total_flats or 0,
        active_sessions=row.active_sessions or 0,
        platform_kwh_month=row.platform_kwh_month or 0,
        platform_sessions_month=row.platform_sessions_month or 0,
        indram_revenue_month=row.indram_revenue_month or 0,
        chargers_online=row.chargers_online or 0,
        chargers_offline=row.chargers_offline or 0,
        fleet_availability_pct=row.fleet_availability_pct or 0,
        fault_rate_pct=row.fault_rate_pct or 0,
        latest_fw_version=row.latest_fw_version,
        chargers_on_latest_fw=row.chargers_on_latest_fw or 0,
        chargers_outdated_fw=row.chargers_outdated_fw or 0,
    )


# ── 2. Society Comparison ────────────────────────────────────────────────────

class SocietyComparisonRow(BaseModel):
    society_id:       int
    society_name:     str
    charger_count:    int
    flat_count:       int
    sessions:         int
    total_kwh:        float
    kwh_per_charger:  float
    indram_revenue:   float
    total_billing:    float
    fault_rate_pct:   float
    availability_pct: float


@router_admin.get("/society-comparison", response_model=list[SocietyComparisonRow])
async def society_comparison(
    month: str | None = Query(None, description="YYYY-MM, defaults to current month"),
    db: AsyncSession  = Depends(get_db),
    _: User           = Depends(require_super_admin),
):
    """
    Per-society aggregated stats for the selected month.

    Uses four CTEs so each aggregation runs against its own optimally-indexed
    path, then joins to the societies table:
      session_stats → idx_sessions_charger_id (via charger) + idx_sessions_ended_status
      billing_stats → monthly_bills_society_id_billing_month_key + idx_flat_bills_monthly
      charger_stats → chargers_flat_id_key UNIQUE + charger_status_charger_id_key UNIQUE
      flat_counts   → idx_flats_society_id

    This is the heaviest endpoint — cache at the application layer (1-hour TTL)
    once data volume grows.
    """
    start, end = _month_bounds(month)

    sql = text("""
        WITH session_stats AS (
            SELECT
                f.society_id,
                COUNT(*)::int                                                      AS sessions,
                COALESCE(SUM(
                    COALESCE(cs.units_consumed,
                             GREATEST(cs.end_meter_kwh - cs.start_meter_kwh, 0.0),
                             0.0)
                ), 0)::float                                                       AS total_kwh,
                COUNT(*) FILTER (
                    WHERE cs.status = 'charging_ended_error'
                )::int                                                             AS fault_sessions
              FROM charging_sessions cs
              JOIN chargers c ON c.charger_id = cs.charger_id
              JOIN flats    f ON f.id          = c.flat_id
             WHERE cs.status  IN ('charging_ended','charging_ended_error','charging_stopped_by_admin')
               AND cs.ended_at >= :start
               AND cs.ended_at  < :end
             GROUP BY f.society_id
        ),
        billing_stats AS (
            SELECT
                m.society_id,
                COALESCE(SUM(mb.total_bill_amount), 0)::float    AS total_billing,
                COALESCE(SUM(fb.indram_charges), 0)::float       AS indram_revenue
              FROM monthly_bills mb
              JOIN meters m ON m.id = mb.meter_id
              -- pre-aggregate so each MSEB bill amount is counted once, not once per flat
              LEFT JOIN (
                    SELECT monthly_bill_id, SUM(indram_charges) AS indram_charges
                      FROM flat_bills
                     GROUP BY monthly_bill_id
              ) fb ON fb.monthly_bill_id = mb.id
             WHERE mb.billing_month >= :start
               AND mb.billing_month  < :end
               AND mb.status = 'sent'
             GROUP BY m.society_id
        ),
        charger_stats AS (
            SELECT
                f.society_id,
                COUNT(c.id)::int                                   AS charger_count,
                COUNT(cs.charger_id) FILTER (
                    WHERE cs.received_at > NOW() - INTERVAL '30 minutes'
                )::int                                             AS chargers_online
              FROM chargers       c
              JOIN flats          f  ON f.id          = c.flat_id
              LEFT JOIN charger_status cs ON cs.charger_id = c.charger_id
             GROUP BY f.society_id
        ),
        flat_counts AS (
            SELECT society_id, COUNT(*)::int AS flat_count
              FROM flats
             GROUP BY society_id
        )
        SELECT
            s.id                                                                 AS society_id,
            s.name                                                               AS society_name,
            COALESCE(chr.charger_count, 0)                                       AS charger_count,
            COALESCE(fc.flat_count, 0)                                           AS flat_count,
            COALESCE(ss.sessions, 0)                                             AS sessions,
            COALESCE(ss.total_kwh, 0)                                            AS total_kwh,
            CASE
                WHEN COALESCE(chr.charger_count, 0) > 0
                THEN ROUND((COALESCE(ss.total_kwh, 0) / chr.charger_count)::numeric, 2)::float
                ELSE 0::float
            END                                                                  AS kwh_per_charger,
            COALESCE(bs.indram_revenue, 0)                                       AS indram_revenue,
            COALESCE(bs.total_billing, 0)                                        AS total_billing,
            CASE
                WHEN COALESCE(ss.sessions, 0) > 0
                THEN ROUND((COALESCE(ss.fault_sessions, 0)::numeric
                             / ss.sessions * 100), 1)::float
                ELSE 0::float
            END                                                                  AS fault_rate_pct,
            CASE
                WHEN COALESCE(chr.charger_count, 0) > 0
                THEN ROUND((COALESCE(chr.chargers_online, 0)::numeric
                             / chr.charger_count * 100), 1)::float
                ELSE 0::float
            END                                                                  AS availability_pct
          FROM societies     s
          LEFT JOIN session_stats  ss  ON ss.society_id  = s.id
          LEFT JOIN billing_stats  bs  ON bs.society_id  = s.id
          LEFT JOIN charger_stats  chr ON chr.society_id = s.id
          LEFT JOIN flat_counts    fc  ON fc.society_id  = s.id
         ORDER BY COALESCE(ss.total_kwh, 0) DESC
    """)

    rows = (await db.execute(sql, {"start": start, "end": end})).all()
    return [
        SocietyComparisonRow(
            society_id=r.society_id,
            society_name=r.society_name,
            charger_count=r.charger_count,
            flat_count=r.flat_count,
            sessions=r.sessions,
            total_kwh=r.total_kwh,
            kwh_per_charger=r.kwh_per_charger,
            indram_revenue=r.indram_revenue,
            total_billing=r.total_billing,
            fault_rate_pct=r.fault_rate_pct,
            availability_pct=r.availability_pct,
        )
        for r in rows
    ]


# ── 3. Firmware Distribution ─────────────────────────────────────────────────

class FirmwareRow(BaseModel):
    fw_version: str | None
    count:      int
    pct:        float


@router_admin.get("/firmware-distribution", response_model=list[FirmwareRow])
async def firmware_distribution(
    society_id: int | None = Query(None, description="Filter to one society"),
    db: AsyncSession = Depends(get_db),
    _: User          = Depends(require_super_admin),
):
    """
    Charger count grouped by firmware version.
    NULL fw_version = charger has never sent a heartbeat.
    Optionally scoped to a single society.
    """
    sid = int(society_id) if society_id else None
    if sid:
        society_join   = f"JOIN flats f ON f.id = c.flat_id"
        society_filter = f"WHERE f.society_id = {sid}"
    else:
        society_join   = ""
        society_filter = ""

    sql = text(f"""
        SELECT
            c.fw_version,
            COUNT(*)::int                                             AS count,
            ROUND(
                COUNT(*)::numeric / NULLIF(SUM(COUNT(*)) OVER (), 0) * 100,
                1
            )::float                                                  AS pct
          FROM chargers c
          {society_join}
          {society_filter}
         GROUP BY c.fw_version
         ORDER BY count DESC
    """)
    rows = (await db.execute(sql)).all()
    return [FirmwareRow(fw_version=r.fw_version, count=r.count, pct=r.pct) for r in rows]


# ── 4. Platform Growth Trend ─────────────────────────────────────────────────

class GrowthTrendRow(BaseModel):
    month:             str     # "YYYY-MM"
    kwh:               float
    sessions:          int
    active_societies:  int


@router_admin.get("/growth-trend", response_model=list[GrowthTrendRow])
async def growth_trend(
    months:    int      = Query(12, ge=1, le=36, description="Look-back window in months"),
    society_id: int | None = Query(None, description="Filter to one society"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    """
    Month-over-month platform kWh, session count, and active society count.
    Optionally scoped to a single society (active_societies will be 0 or 1 in that case).
    """
    sid = int(society_id) if society_id else None
    society_filter = f"AND f.society_id = {sid}" if sid else ""

    sql = text(f"""
        SELECT
            TO_CHAR(DATE_TRUNC('month', cs.ended_at), 'YYYY-MM')      AS month,
            COALESCE(SUM(
                COALESCE(cs.units_consumed,
                         GREATEST(cs.end_meter_kwh - cs.start_meter_kwh, 0.0),
                         0.0)
            ), 0)::float                                               AS kwh,
            COUNT(*)::int                                              AS sessions,
            COUNT(DISTINCT f.society_id)::int                         AS active_societies
          FROM charging_sessions cs
          JOIN chargers c ON c.charger_id = cs.charger_id
          JOIN flats    f ON f.id          = c.flat_id
         WHERE cs.status   IN ('charging_ended','charging_ended_error','charging_stopped_by_admin')
           AND cs.ended_at >= NOW() - (INTERVAL '1 month' * :months)
           {society_filter}
         GROUP BY DATE_TRUNC('month', cs.ended_at)
         ORDER BY DATE_TRUNC('month', cs.ended_at) ASC
    """)
    rows = (await db.execute(sql, {"months": months})).all()
    return [
        GrowthTrendRow(
            month=r.month,
            kwh=r.kwh,
            sessions=r.sessions,
            active_societies=r.active_societies,
        )
        for r in rows
    ]


@router_admin.post("/download-report")
async def admin_download_report(
    req: DownloadReportRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    """
    Downloadable report for the selected month.
    If req.society_id is provided, the report is scoped to that society;
    otherwise it covers the entire platform.
    """
    start, end = _month_bounds(req.month)
    fmt        = req.format.lower()
    if fmt not in ("csv", "excel", "pdf"):
        raise HTTPException(400, "format must be csv, excel, or pdf")

    # Build optional society JOIN/filter — req.society_id is validated int|None,
    # safe to interpolate directly (same pattern used in platform_overview).
    sid = int(req.society_id) if req.society_id else None
    if sid:
        society_join   = f"JOIN chargers _c2 ON _c2.charger_id = cs.charger_id JOIN flats _f2 ON _f2.id = _c2.flat_id"
        society_filter = f"AND _f2.society_id = {sid}"
    else:
        society_join   = ""
        society_filter = ""

    data: dict = {}

    # Energy — optionally scoped to one society
    energy_sql = text(f"""
        SELECT
            DATE(cs.ended_at)::text AS date,
            COALESCE(SUM(COALESCE(cs.units_consumed,
                GREATEST(cs.end_meter_kwh - cs.start_meter_kwh, 0.0), 0.0)), 0)::float AS kwh,
            COUNT(*) FILTER (WHERE cs.status = 'charging_ended_error')::int AS fault_sessions,
            COUNT(*)::int AS total_sessions
          FROM charging_sessions cs
          {society_join}
         WHERE cs.status = ANY(:statuses)
           AND cs.ended_at >= :start AND cs.ended_at < :end
           {society_filter}
         GROUP BY DATE(cs.ended_at) ORDER BY date
    """)
    data["energy"] = (await db.execute(
        energy_sql,
        {"statuses": list(ENDED_STATUSES), "start": start, "end": end},
    )).all()

    # Faults — optionally scoped to one society
    if fmt != "csv":
        faults_sql = text(f"""
            SELECT cs.fault_code,
                   COUNT(*)::int AS count,
                   AVG(cs.temperature_c)::float AS avg_temp_c,
                   ARRAY_AGG(DISTINCT cs.charger_id) AS chargers_affected
              FROM charging_sessions cs
              {society_join}
             WHERE cs.fault_code IS NOT NULL
               AND cs.fault_code NOT IN ('0', '', 'null', 'FC_OK', 'none', 'None')
               AND cs.ended_at >= :start AND cs.ended_at < :end
               {society_filter}
             GROUP BY cs.fault_code ORDER BY count DESC
        """)
        data["faults"] = (await db.execute(
            faults_sql, {"start": start, "end": end}
        )).all()

    scope         = f"society-{sid}" if sid else "platform"
    filename_base = f"indram-{scope}-report-{req.month}"
    if fmt == "csv":
        return _render_csv(data, filename_base)
    elif fmt == "excel":
        return _render_excel(data, filename_base, req.month)
    else:
        return _render_pdf(data, filename_base, req.month)

# ═════════════════════════════════════════════════════════════════════════════
#  SUPER ADMIN — SOCIETY DETAIL ENDPOINTS
#  Mirror of the society-admin endpoints, but accessible by super admin.
#  All require an explicit society_id query parameter.
#  Registered under /api/analytics/admin/society-detail/...
# ═════════════════════════════════════════════════════════════════════════════

@router_admin.get("/society-detail/daily-energy", response_model=list[DailyEnergyRow])
async def admin_society_daily_energy(
    society_id: int      = Query(..., description="Society to view"),
    month: str | None    = Query(None, description="YYYY-MM, defaults to current month"),
    db: AsyncSession     = Depends(get_db),
    _: User              = Depends(require_super_admin),
):
    """Daily kWh + fault count for one society — super admin access."""
    start, end = _month_bounds(month)
    sql = text("""
        WITH sc AS (
            SELECT c.charger_id
              FROM chargers c JOIN flats f ON f.id = c.flat_id
             WHERE f.society_id = :sid
        )
        SELECT
            DATE(cs.ended_at)::text                                       AS date,
            COALESCE(SUM(
                COALESCE(cs.units_consumed,
                         GREATEST(cs.end_meter_kwh - cs.start_meter_kwh, 0.0),
                         0.0)
            ), 0)::float                                                  AS kwh,
            COUNT(*) FILTER (
                WHERE cs.status = 'charging_ended_error'
            )::int                                                        AS fault_sessions,
            COUNT(*)::int                                                 AS total_sessions
          FROM charging_sessions cs
         WHERE cs.charger_id  IN (SELECT charger_id FROM sc)
           AND cs.status       = ANY(:statuses)
           AND cs.ended_at    >= :start
           AND cs.ended_at     < :end
         GROUP BY DATE(cs.ended_at)
         ORDER BY date
    """)
    rows = (await db.execute(
        sql,
        {"sid": society_id, "statuses": list(ENDED_STATUSES), "start": start, "end": end},
    )).all()
    return [
        DailyEnergyRow(
            date=r.date, kwh=r.kwh,
            fault_sessions=r.fault_sessions, total_sessions=r.total_sessions,
        )
        for r in rows
    ]


@router_admin.get("/society-detail/peak-hours", response_model=list[PeakHourRow])
async def admin_society_peak_hours(
    society_id: int      = Query(...),
    month: str | None    = Query(None),
    db: AsyncSession     = Depends(get_db),
    _: User              = Depends(require_super_admin),
):
    """7×24 session heatmap for one society — super admin access."""
    start, end = _month_bounds(month)
    sql = text("""
        WITH sc AS (
            SELECT c.charger_id
              FROM chargers c JOIN flats f ON f.id = c.flat_id
             WHERE f.society_id = :sid
        )
        SELECT
            EXTRACT(DOW  FROM cs.started_at)::int  AS dow,
            EXTRACT(HOUR FROM cs.started_at)::int  AS hour,
            COUNT(*)::int                           AS count
          FROM charging_sessions cs
         WHERE cs.charger_id  IN (SELECT charger_id FROM sc)
           AND cs.started_at >= :start
           AND cs.started_at  < :end
         GROUP BY EXTRACT(DOW FROM cs.started_at),
                  EXTRACT(HOUR FROM cs.started_at)
         ORDER BY dow, hour
    """)
    rows = (await db.execute(sql, {"sid": society_id, "start": start, "end": end})).all()
    return [PeakHourRow(dow=r.dow, hour=r.hour, count=r.count) for r in rows]


@router_admin.get("/society-detail/charger-health", response_model=list[ChargerHealthRow])
async def admin_society_charger_health(
    society_id: int      = Query(...),
    db: AsyncSession     = Depends(get_db),
    _: User              = Depends(require_super_admin),
):
    """Live charger status for one society — super admin access."""
    sql = text("""
        SELECT
            c.charger_id, f.flat_number,
            cs.charger_status,
            cs.voltage::float, cs.current::float,
            cs.energy_kwh::float, cs.temperature_c::float,
            cs.duration_min, cs.fault_code, cs.received_at,
            c.fw_version, c.is_active
          FROM chargers       c
          JOIN flats          f  ON f.id         = c.flat_id
          LEFT JOIN charger_status cs ON cs.charger_id = c.charger_id
         WHERE f.society_id = :sid
         ORDER BY c.charger_id
    """)
    rows = (await db.execute(sql, {"sid": society_id})).all()
    result = []
    for r in rows:
        status    = r.charger_status
        fault     = r.fault_code
        last_seen = r.received_at
        if fault and fault not in _NOT_A_FAULT:
            status = "fault"
        elif last_seen is None or (
            datetime.now(timezone.utc) - last_seen
        ).total_seconds() > OFFLINE_THRESHOLD_MINUTES * 60:
            status = "offline"
        result.append(ChargerHealthRow(
            charger_id=r.charger_id, flat_number=r.flat_number,
            charger_status=status, voltage=r.voltage, current=r.current,
            energy_kwh=r.energy_kwh, temperature_c=r.temperature_c,
            duration_min=r.duration_min, fault_code=fault,
            last_seen_at=last_seen.isoformat() if last_seen else None,
            fw_version=r.fw_version, is_active=r.is_active,
        ))
    return result


@router_admin.get("/society-detail/fault-analysis", response_model=FaultAnalysisOut)
async def admin_society_fault_analysis(
    society_id: int      = Query(...),
    months: int          = Query(3, ge=1, le=24),
    db: AsyncSession     = Depends(get_db),
    _: User              = Depends(require_super_admin),
):
    """Fault code breakdown for one society — super admin access."""
    sql = text("""
        WITH sc AS (
            SELECT c.charger_id
              FROM chargers c JOIN flats f ON f.id = c.flat_id
             WHERE f.society_id = :sid
        )
        SELECT
            cs.fault_code,
            COUNT(*)::int                       AS count,
            AVG(cs.temperature_c)::float        AS avg_temp_c,
            ARRAY_AGG(DISTINCT cs.charger_id)   AS chargers_affected
          FROM charging_sessions cs
         WHERE cs.charger_id IN (SELECT charger_id FROM sc)
           AND cs.fault_code IS NOT NULL
           AND cs.fault_code NOT IN ('0', '', 'null', 'FC_OK', 'none', 'None')
           AND cs.ended_at  >= NOW() - (:months * INTERVAL '1 month')
         GROUP BY cs.fault_code
         ORDER BY count DESC
    """)
    rows = (await db.execute(sql, {"sid": society_id, "months": months})).all()
    if not rows:
        return FaultAnalysisOut(fault_summary=[], top_offender_charger=None, avg_temp_at_fault=None)
    fault_summary = [
        FaultSummaryItem(
            fault_code=r.fault_code, count=r.count,
            avg_temp_c=_safe_float(r.avg_temp_c),
            chargers_affected=list(r.chargers_affected or []),
        )
        for r in rows
    ]
    top_sql = text("""
        WITH sc AS (
            SELECT c.charger_id
              FROM chargers c JOIN flats f ON f.id = c.flat_id
             WHERE f.society_id = :sid
        )
        SELECT cs.charger_id, COUNT(*) AS n
          FROM charging_sessions cs
         WHERE cs.charger_id IN (SELECT charger_id FROM sc)
           AND cs.fault_code IS NOT NULL
           AND cs.fault_code NOT IN ('0', '', 'null', 'FC_OK', 'none', 'None')
           AND cs.ended_at  >= NOW() - (:months * INTERVAL '1 month')
         GROUP BY cs.charger_id ORDER BY n DESC LIMIT 1
    """)
    top_row = (await db.execute(top_sql, {"sid": society_id, "months": months})).first()
    avg_temp_at_fault = (
        sum(r.avg_temp_c * r.count for r in rows if r.avg_temp_c is not None)
        / sum(r.count for r in rows if r.avg_temp_c is not None)
        if any(r.avg_temp_c is not None for r in rows)
        else None
    )
    return FaultAnalysisOut(
        fault_summary=fault_summary,
        top_offender_charger=top_row.charger_id if top_row else None,
        avg_temp_at_fault=avg_temp_at_fault,
    )


@router_admin.get("/society-detail/session-duration", response_model=list[SessionDurationRow])
async def admin_society_session_duration(
    society_id: int      = Query(...),
    month: str | None    = Query(None),
    db: AsyncSession     = Depends(get_db),
    _: User              = Depends(require_super_admin),
):
    """Session duration histogram for one society — super admin access."""
    start, end = _month_bounds(month)
    sql = text("""
        WITH sc AS (
            SELECT c.charger_id
              FROM chargers c JOIN flats f ON f.id = c.flat_id
             WHERE f.society_id = :sid
        ),
        durations AS (
            SELECT EXTRACT(EPOCH FROM (cs.ended_at - cs.started_at)) / 60.0 AS dur_min
              FROM charging_sessions cs
             WHERE cs.charger_id IN (SELECT charger_id FROM sc)
               AND cs.status      = ANY(:statuses)
               AND cs.ended_at   >= :start AND cs.ended_at < :end
               AND cs.ended_at IS NOT NULL AND cs.started_at IS NOT NULL
        )
        SELECT
            CASE WHEN dur_min<30 THEN 1 WHEN dur_min<60 THEN 2
                 WHEN dur_min<120 THEN 3 WHEN dur_min<240 THEN 4 ELSE 5 END AS sort_key,
            CASE WHEN dur_min<30 THEN '0–30 min' WHEN dur_min<60 THEN '30–60 min'
                 WHEN dur_min<120 THEN '1–2 hrs' WHEN dur_min<240 THEN '2–4 hrs'
                 ELSE '4+ hrs' END AS bucket_label,
            COUNT(*)::int AS count
          FROM durations
         GROUP BY sort_key, bucket_label ORDER BY sort_key
    """)
    rows = (await db.execute(
        sql, {"sid": society_id, "statuses": list(ENDED_STATUSES), "start": start, "end": end},
    )).all()
    bucket_order = ["0–30 min", "30–60 min", "1–2 hrs", "2–4 hrs", "4+ hrs"]
    counts = {r.bucket_label: r.count for r in rows}
    return [SessionDurationRow(bucket_label=b, count=counts.get(b, 0)) for b in bucket_order]


@router_admin.get("/society-detail/billing-trend", response_model=list[BillingTrendRow])
async def admin_society_billing_trend(
    society_id: int      = Query(...),
    months: int          = Query(6, ge=1, le=24),
    db: AsyncSession     = Depends(get_db),
    _: User              = Depends(require_super_admin),
):
    """Monthly billing trend for one society — super admin access."""
    sql = text("""
        SELECT
            TO_CHAR(mb.billing_month, 'YYYY-MM')              AS month,
            mb.total_bill_amount::float,
            mb.total_units_consumed::float,
            mb.effective_unit_rate::float,
            COALESCE(SUM(fb.indram_charges), 0)::float        AS indram_charges_total,
            COUNT(*) FILTER (WHERE fb.email_status = 'sent')::int   AS emails_sent,
            COUNT(*) FILTER (WHERE fb.email_status = 'failed')::int AS emails_failed
          FROM monthly_bills mb
          JOIN meters m ON m.id = mb.meter_id
          LEFT JOIN flat_bills fb ON fb.monthly_bill_id = mb.id
         WHERE m.society_id = :sid
           AND mb.status = 'sent'
         GROUP BY mb.id, mb.billing_month, mb.total_bill_amount,
                  mb.total_units_consumed, mb.effective_unit_rate
         ORDER BY mb.billing_month DESC
         LIMIT :months
    """)
    rows = (await db.execute(sql, {"sid": society_id, "months": months})).all()
    return [
        BillingTrendRow(
            month=r.month,
            total_bill_amount=r.total_bill_amount,
            total_units_consumed=r.total_units_consumed,
            effective_unit_rate=r.effective_unit_rate,
            indram_charges_total=r.indram_charges_total,
            emails_sent=r.emails_sent,
            emails_failed=r.emails_failed,
        )
        for r in rows
    ]