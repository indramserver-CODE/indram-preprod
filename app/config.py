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
    # Must be unique per running instance on the broker. preprod and prod share
    # a HiveMQ cluster, so each environment needs its own value.
    MQTT_CLIENT_ID: str = "evc-server-prod"

    # CORS — "*" opens everything (local dev); set a comma-separated list in production
    CORS_ORIGINS: str = "*"

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

    # Indram details printed on the GST tax invoice (override in .env if they change)
    INDRAM_LEGAL_NAME:    str = "Indram Techventure Pvt. Ltd."
    INDRAM_ADDRESS:       str = ("Indram Techventures Pvt. Ltd.\n"
                                 "Mother Teresa Flyover, above Exide Battery, Adarsh Nagar\n"
                                 "Pune Maharashtra 411017\nIndia")
    INDRAM_GSTIN:         str = "27AAICI5926L1Z2"
    INDRAM_PHONE:         str = "91-9960159031"
    INDRAM_EMAIL:         str = "int.indram@gmail.com"
    INDRAM_STATE_CODE:    str = "27"                     # place of supply when the society has no GSTIN
    INDRAM_INVOICE_ITEM:  str = "Charger Maintenance"
    INDRAM_INVOICE_SAC:   str = "998739"
    INDRAM_INVOICE_NOTES: str = "Thanks for your business."

    # MQTT command auth token (must match CMD_AUTH_TOKEN in charger firmware)
    CMD_AUTH_TOKEN: str = ""

    # Super admin seed
    SUPER_ADMIN_EMAIL:    str = ""
    SUPER_ADMIN_PASSWORD: str = ""


settings = Settings()