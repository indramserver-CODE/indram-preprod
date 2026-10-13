"""
app/services/storage.py
-----------------------
S3 helpers for bill PDFs, MSEB bill photos and society letterheads.
Every call is a no-op (returns None) when S3_BUCKET_NAME is not configured.
"""

import logging

import boto3

from app.config import settings

logger = logging.getLogger(__name__)


def _client():
    return boto3.client("s3", region_name=settings.AWS_REGION,
                        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY)


def upload(file_bytes: bytes, s3_key: str, content_type: str = "application/pdf") -> str | None:
    if not settings.S3_BUCKET_NAME:
        return None
    try:
        _client().put_object(Bucket=settings.S3_BUCKET_NAME, Key=s3_key,
                             Body=file_bytes, ContentType=content_type)
        return s3_key
    except Exception as e:
        logger.error("S3 upload failed | key=%s error=%s", s3_key, e)
        return None


def download(s3_key: str | None) -> bytes | None:
    if not s3_key or not settings.S3_BUCKET_NAME:
        return None
    try:
        return _client().get_object(Bucket=settings.S3_BUCKET_NAME, Key=s3_key)["Body"].read()
    except Exception as e:
        logger.error("S3 download failed | key=%s error=%s", s3_key, e)
        return None


def presigned_url(s3_key: str | None, expires_s: int = 900) -> str | None:
    if not s3_key or not settings.S3_BUCKET_NAME:
        return None
    try:
        return _client().generate_presigned_url(
            "get_object", Params={"Bucket": settings.S3_BUCKET_NAME, "Key": s3_key}, ExpiresIn=expires_s,
        )
    except Exception as e:
        logger.error("S3 presign failed | key=%s error=%s", s3_key, e)
        return None
