"""
app/services/scheduler.py
-------------------------
Daily billing jobs (APScheduler, Indian time). Started from main.lifespan when
ENABLE_SCHEDULER=true — enable it on one instance only. Reminders are claimed with
an atomic UPDATE, so even two schedulers never email the same reminder twice.

  09:00  send_due_reminders — one email per bill, 2 days before its due date:
           residents: sent bills still pending
           society admins: issued Indram invoices still unpaid
         Bills due within the window are still reminded if a run was missed,
         as long as the due date hasn't passed.
"""

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, update

from app.models.bill import MonthlyBill, FlatBill, IndramBill
from app.models.meter import Meter
from app.models.society import Society
from app.services import billing_calc as bc
from app.services.bill_dispatch import society_admin_emails
from app.services.email_service import send_payment_reminder_email, send_invoice_reminder_email

logger = logging.getLogger(__name__)

REMINDER_DAYS_BEFORE = 2

_scheduler: AsyncIOScheduler | None = None


async def _remind_residents(db, today, until) -> int:
    claimed = (await db.execute(
        update(FlatBill)
        .where(
            FlatBill.monthly_bill_id.in_(
                select(MonthlyBill.id).where(MonthlyBill.status == "sent",
                                             MonthlyBill.due_date >= today, MonthlyBill.due_date <= until)
            ),
            FlatBill.payment_status == "pending",
            FlatBill.reminder_sent_at.is_(None),
            FlatBill.email.is_not(None),
        )
        .values(reminder_sent_at=datetime.now(timezone.utc))
        .returning(FlatBill.id)
    )).scalars().all()
    await db.commit()

    sent = 0
    for fb_id in claimed:
        fb = await db.get(FlatBill, fb_id)
        mb = await db.get(MonthlyBill, fb.monthly_bill_id)
        society_name = await db.scalar(
            select(Society.name).join(Meter, Meter.society_id == Society.id).where(Meter.id == mb.meter_id)
        )
        ok = await send_payment_reminder_email(
            to_email=fb.email, owner_name=fb.owner_name, flat_number=fb.flat_number,
            society_name=society_name, bill_number=fb.bill_number,
            total_payable=fb.total_payable, due_date=mb.due_date,
        )
        if ok:
            sent += 1
        else:
            fb.reminder_sent_at = None   # release the claim — tomorrow's run retries
            await db.commit()
    return sent


async def _remind_societies(db, today, until) -> int:
    claimed = (await db.execute(
        update(IndramBill)
        .where(IndramBill.status == "issued", IndramBill.payment_status == "unpaid",
               IndramBill.due_date >= today, IndramBill.due_date <= until,
               IndramBill.reminder_sent_at.is_(None))
        .values(reminder_sent_at=datetime.now(timezone.utc))
        .returning(IndramBill.id)
    )).scalars().all()
    await db.commit()

    sent = 0
    for inv_id in claimed:
        inv     = await db.get(IndramBill, inv_id)
        society = await db.get(Society, inv.society_id)
        ok = False
        for to in await society_admin_emails(db, society.id):
            ok = await send_invoice_reminder_email(
                to_email=to, society_name=society.name, invoice_number=inv.invoice_number,
                total_payable=inv.total_payable, due_date=inv.due_date,
            ) or ok
        if ok:
            sent += 1
        else:
            inv.reminder_sent_at = None
            await db.commit()
    return sent


async def send_due_reminders():
    from app.database import AsyncSessionLocal

    today = bc.today_ist()
    until = today + timedelta(days=REMINDER_DAYS_BEFORE)
    try:
        async with AsyncSessionLocal() as db:
            residents = await _remind_residents(db, today, until)
            societies = await _remind_societies(db, today, until)
        logger.info("Due reminders sent | residents=%s societies=%s (due %s..%s)", residents, societies, today, until)
    except Exception as e:
        logger.exception("Due reminder job failed | error=%s", e)


def start_scheduler():
    global _scheduler
    _scheduler = AsyncIOScheduler(timezone=bc.IST)
    _scheduler.add_job(send_due_reminders, "cron", hour=9, minute=0, id="due_reminders",
                       coalesce=True, misfire_grace_time=6 * 3600, replace_existing=True)
    _scheduler.start()
    logger.info("Billing scheduler started — reminders daily at 09:00 IST")


def stop_scheduler():
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
