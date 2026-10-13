from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class PasswordResetToken(Base):
    """
    Hashed, single-use, time-limited password reset tokens.
    The raw token is emailed to the user and never stored — only its
    SHA-256 hash lives here, mirroring how we never store plaintext
    passwords.
    """
    __tablename__ = "password_reset_tokens"

    id:         Mapped[int]           = mapped_column(primary_key=True)
    user_id:    Mapped[int]           = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str]           = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime]      = mapped_column(DateTime(timezone=True), nullable=False)
    used_at:    Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now())