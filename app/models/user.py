from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id:              Mapped[int]      = mapped_column(primary_key=True)
    email:           Mapped[str]      = mapped_column(String(255), nullable=False, unique=True)
    hashed_password: Mapped[str]      = mapped_column(String(255), nullable=False)
    full_name:       Mapped[str|None] = mapped_column(String(255))
    role:            Mapped[str]      = mapped_column(String(50), nullable=False)   # 'super_admin' | 'society_admin'
    is_active:       Mapped[bool]     = mapped_column(Boolean, default=True)
    created_at:      Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    society_admins: Mapped[list["SocietyAdmin"]] = relationship("SocietyAdmin", back_populates="user", cascade="all, delete-orphan")


class SocietyAdmin(Base):
    __tablename__ = "society_admins"

    user_id:     Mapped[int]      = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    society_id:  Mapped[int]      = mapped_column(ForeignKey("societies.id", ondelete="CASCADE"), primary_key=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user:    Mapped["User"]    = relationship("User", back_populates="society_admins")
    society: Mapped["Society"] = relationship("Society", back_populates="society_admins")
