"""
app/routers/society_settings.py
-------------------------------
Society admin: their own society's billing settings.

GET    /api/sa/society                    — profile, payment details, late fee settings (read-only)
PUT    /api/sa/society/payment-details    — printed on every resident bill
PUT    /api/sa/society/letterhead         — header image (PNG/JPG, ≤ 2 MB) for bills and receipts
GET    /api/sa/society/letterhead         — current letterhead image
DELETE /api/sa/society/letterhead         — remove it (bills fall back to a plain name header)

Late fee %, grace days, Indram rate and GSTIN are set by the super admin (PUT /api/societies/{id}).
"""

import io
import logging
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import Response
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies.auth import require_society_admin
from app.models.society import Society
from app.models.user import SocietyAdmin, User
from app.services import storage
from app.services.billing_calc import DEFAULT_INDRAM_RATE

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_LETTERHEAD_BYTES = 2 * 1024 * 1024
LETTERHEAD_FORMATS   = {"PNG": "image/png", "JPEG": "image/jpeg"}


class PaymentDetails(BaseModel):
    payee_name:      str | None = Field(None, max_length=255)
    bank_name:       str | None = Field(None, max_length=255)
    bank_account_no: str | None = Field(None, max_length=50)
    bank_ifsc:       str | None = Field(None, max_length=20)
    upi_id:          str | None = Field(None, max_length=100)
    payment_note:    str | None = None


class SocietySettingsOut(PaymentDetails):
    id:                           int
    name:                         str
    address:                      str | None
    gstin:                        str | None
    indram_rate:                  Decimal
    resident_late_fee_pct:        Decimal
    resident_late_fee_grace_days: int
    indram_late_fee_pct:          Decimal
    indram_late_fee_grace_days:   int
    has_letterhead:               bool
    created_at:                   datetime


async def _my_society(user: User, db: AsyncSession) -> Society:
    society_id = await db.scalar(select(SocietyAdmin.society_id).where(SocietyAdmin.user_id == user.id))
    if not society_id:
        raise HTTPException(status_code=403, detail="No society assigned")
    society = await db.get(Society, society_id)
    if not society:
        raise HTTPException(status_code=404, detail="Society not found")
    return society


def _out(s: Society) -> SocietySettingsOut:
    return SocietySettingsOut(
        id=s.id, name=s.name, address=s.address, gstin=s.gstin,
        indram_rate=s.indram_rate if s.indram_rate is not None else DEFAULT_INDRAM_RATE,
        resident_late_fee_pct=s.resident_late_fee_pct, resident_late_fee_grace_days=s.resident_late_fee_grace_days,
        indram_late_fee_pct=s.indram_late_fee_pct, indram_late_fee_grace_days=s.indram_late_fee_grace_days,
        payee_name=s.payee_name, bank_name=s.bank_name, bank_account_no=s.bank_account_no,
        bank_ifsc=s.bank_ifsc, upi_id=s.upi_id, payment_note=s.payment_note,
        has_letterhead=bool(s.letterhead_s3_key), created_at=s.created_at,
    )


@router.get("", response_model=SocietySettingsOut)
async def get_settings(db: AsyncSession = Depends(get_db), user: User = Depends(require_society_admin)):
    return _out(await _my_society(user, db))


@router.put("/payment-details", response_model=SocietySettingsOut)
async def update_payment_details(body: PaymentDetails, db: AsyncSession = Depends(get_db),
                                 user: User = Depends(require_society_admin)):
    society = await _my_society(user, db)
    for field, value in body.model_dump().items():
        setattr(society, field, value.strip() if isinstance(value, str) and value.strip() else None)
    await db.commit()
    return _out(society)


@router.put("/letterhead", response_model=SocietySettingsOut)
async def upload_letterhead(file: UploadFile = File(...), db: AsyncSession = Depends(get_db),
                            user: User = Depends(require_society_admin)):
    if not settings.S3_BUCKET_NAME:
        raise HTTPException(status_code=503, detail="File storage is not configured, so a letterhead can't be saved.")
    society = await _my_society(user, db)

    data = await file.read(MAX_LETTERHEAD_BYTES + 1)
    if len(data) > MAX_LETTERHEAD_BYTES:
        raise HTTPException(status_code=413, detail="Letterhead must be 2 MB or smaller.")
    try:
        with Image.open(io.BytesIO(data)) as img:
            fmt = img.format
            img.verify()
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise HTTPException(status_code=400, detail="Letterhead must be a PNG or JPG image.")
    if fmt not in LETTERHEAD_FORMATS:
        raise HTTPException(status_code=400, detail="Letterhead must be a PNG or JPG image.")

    ext = "png" if fmt == "PNG" else "jpg"
    key = storage.upload(data, f"letterheads/{society.id}/letterhead-{datetime.now():%Y%m%d%H%M%S}.{ext}",
                         LETTERHEAD_FORMATS[fmt])
    if not key:
        raise HTTPException(status_code=502, detail="Couldn't save the letterhead — please try again.")
    society.letterhead_s3_key = key
    await db.commit()
    logger.info("Letterhead uploaded | society=%s key=%s", society.id, key)
    return _out(society)


@router.get("/letterhead")
async def get_letterhead(db: AsyncSession = Depends(get_db), user: User = Depends(require_society_admin)):
    society = await _my_society(user, db)
    data = storage.download(society.letterhead_s3_key)
    if not data:
        raise HTTPException(status_code=404, detail="No letterhead uploaded.")
    media = "image/png" if society.letterhead_s3_key.endswith(".png") else "image/jpeg"
    return Response(content=data, media_type=media)


@router.delete("/letterhead", status_code=status.HTTP_204_NO_CONTENT)
async def delete_letterhead(db: AsyncSession = Depends(get_db), user: User = Depends(require_society_admin)):
    society = await _my_society(user, db)
    society.letterhead_s3_key = None   # old file stays in S3 — earlier bills' stored PDFs already embed it
    await db.commit()
