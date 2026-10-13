"""
app/config.py
-------------
All configuration is read from environment variables (or a .env file).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"   # ✅ prevents crash for unknown env vars
    )

    # Database (Neon PostgreSQL)
    DATABASE_URL: str

    # ✅ ADD THIS (MAIN FIX)
    ENABLE_MQTT: bool = False

    # MQTT (Mosquitto / HiveMQ)
    MQTT_HOST:     str  = "localhost"
    MQTT_PORT:     int  = 1883
    MQTT_USERNAME: str  = ""
    MQTT_PASSWORD: str  = ""
    MQTT_USE_TLS:  bool = False

    # JWT Auth
    SECRET_KEY:         str  = "change-me-in-production"
    ALGORITHM:          str  = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8

    # Password reset
    PASSWORD_RESET_EXPIRE_MINUTES: int = 30
    FRONTEND_URL: str = "http://localhost:5173"

    # AWS (S3 for bill PDFs — optional)
    AWS_REGION:            str = "ap-south-1"
    AWS_ACCESS_KEY_ID:     str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    S3_BUCKET_NAME:        str = ""

    # Email — Gmail SMTP
    GMAIL_USER:            str = ""
    GMAIL_APP_PASSWORD:    str = ""

    # Billing cron
    BILLING_DAY_OF_MONTH: int = 1
    ENABLE_SCHEDULER: bool = False   # run reminder jobs — enable on exactly one instance

    # Indram details printed on the GST tax invoice
    INDRAM_LEGAL_NAME: str = "Indram"
    INDRAM_ADDRESS:    str = ""
    INDRAM_GSTIN:      str = ""

    # MQTT command auth token (must match CMD_AUTH_TOKEN in charger firmware)
    CMD_AUTH_TOKEN: str = ""

    # Super admin seed
    SUPER_ADMIN_EMAIL:    str = ""
    SUPER_ADMIN_PASSWORD: str = ""


settings = Settings()