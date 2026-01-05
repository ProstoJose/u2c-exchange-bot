from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    language_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    give_currency: Mapped[str] = mapped_column(String(8), nullable=False)
    get_currency: Mapped[str] = mapped_column(String(8), nullable=False)

    amount_mode: Mapped[str] = mapped_column(String(16), nullable=False)  # give|get
    amount_value: Mapped[float] = mapped_column(Float, nullable=False)

    from_location: Mapped[str] = mapped_column(String(256), nullable=False)
    to_location: Mapped[str] = mapped_column(String(256), nullable=False)

    rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    calculated_give: Mapped[float | None] = mapped_column(Float, nullable=True)
    calculated_get: Mapped[float | None] = mapped_column(Float, nullable=True)
    sources: Mapped[str | None] = mapped_column(Text, nullable=True)

    contact: Mapped[str | None] = mapped_column(String(256), nullable=True)

    stage: Mapped[str] = mapped_column(String(16), nullable=False, default="calc")  # calc|submitted
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RateCache(Base):
    __tablename__ = "rates_cache"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

