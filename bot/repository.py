from __future__ import annotations

import csv
import io
from datetime import datetime

from aiogram.types import User as TgUser
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .db import utcnow
from .models import Order, RateCache, User


async def upsert_user(session: AsyncSession, tg: TgUser) -> None:
    now = utcnow()
    existing = await session.get(User, tg.id)
    if existing is None:
        session.add(User(
            user_id=tg.id,
            username=tg.username,
            first_name=tg.first_name,
            last_name=tg.last_name,
            language_code=tg.language_code,
            created_at=now,
            last_seen_at=now,
            is_blocked=False,
        ))
        await session.commit()
        return

    existing.username = tg.username
    existing.first_name = tg.first_name
    existing.last_name = tg.last_name
    existing.language_code = tg.language_code
    existing.last_seen_at = now
    await session.commit()


async def create_order(
    session: AsyncSession,
    user_id: int,
    give_currency: str,
    get_currency: str,
    amount_mode: str,
    amount_value: float,
    from_location: str,
    to_location: str,
) -> Order:
    now = utcnow()
    order = Order(
        user_id=user_id,
        give_currency=give_currency,
        get_currency=get_currency,
        amount_mode=amount_mode,
        amount_value=amount_value,
        from_location=from_location,
        to_location=to_location,
        stage="calc",
        created_at=now,
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return order


async def set_order_calc(
    session: AsyncSession,
    order_id: int,
    rate: float,
    calculated_give: float,
    calculated_get: float,
    sources: str,
) -> None:
    order = await session.get(Order, order_id)
    if order is None:
        return
    order.rate = rate
    order.calculated_give = calculated_give
    order.calculated_get = calculated_get
    order.sources = sources
    await session.commit()


async def set_order_contact_and_submit(
    session: AsyncSession,
    order_id: int,
    contact: str,
) -> None:
    order = await session.get(Order, order_id)
    if order is None:
        return
    order.contact = contact
    order.stage = "submitted"
    await session.commit()


async def export_users_csv(session: AsyncSession) -> bytes:
    q = await session.execute(select(User).order_by(User.created_at.asc()))
    users = q.scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "user_id", "username", "first_name", "last_name", "language", "created_at", "last_seen_at", "is_blocked"
    ])
    for u in users:
        writer.writerow([
            u.user_id,
            u.username or "",
            u.first_name or "",
            u.last_name or "",
            u.language_code or "",
            u.created_at.isoformat(),
            u.last_seen_at.isoformat(),
            int(u.is_blocked),
        ])

    return buf.getvalue().encode("utf-8")
