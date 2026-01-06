from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message, BufferedInputFile

from .config import Config, load_config
from .db import create_engine_and_sessionmaker, init_db
from .keyboards import CURRENCIES, kbd_amount_mode, kbd_choose_currency, kbd_show_rate, kbd_start, kbd_submit
from .rates.service import RateService
from .repository import create_order, export_users_csv, set_order_calc, set_order_contact_and_submit, upsert_user
from .states import ExchangeFlow

router = Router()


def _user_label(msg_user) -> str:
    if msg_user.username:
        return f"@{msg_user.username}"
    name = (msg_user.first_name or "") + (" " + msg_user.last_name if msg_user.last_name else "")
    name = name.strip() or "(без username)"
    return f"{name} (id:{msg_user.id})"


def _parse_amount(text: str) -> float | None:
    t = (text or "").strip().replace(" ", "").replace(",", ".")
    try:
        v = float(t)
        if v <= 0:
            return None
        return v
    except ValueError:
        return None


def _round_money_no_cents(x: float) -> int:
    return int(round(x))


def _sources_to_text(path) -> str:
    if not path:
        return ""
    parts = []
    for a, b, src in path:
        parts.append(f"{a}->{b}({src})")
    return " | ".join(parts)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db_session_factory) -> None:
    await state.clear()
    async with db_session_factory() as db:
        await upsert_user(db, message.from_user)
    await message.answer(
        "Привет! Я бот обменника.\n\nНажми *Начать расчёт*, чтобы посчитать курс и отправить заявку.",
        reply_markup=kbd_start(),
        parse_mode=ParseMode.MARKDOWN,
    )


@router.callback_query(F.data == "start_calc")
async def start_calc(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ExchangeFlow.choose_give)
    await state.update_data()
    await call.message.edit_text(
        "Выберите валюту *Отдаёте*:",
        reply_markup=kbd_choose_currency("give"),
        parse_mode=ParseMode.MARKDOWN,
    )
    await call.answer()


@router.callback_query(F.data.startswith("give:"))
async def choose_give(call: CallbackQuery, state: FSMContext) -> None:
    give = call.data.split(":", 1)[1]
    if give not in CURRENCIES:
        await call.answer("Неизвестная валюта", show_alert=True)
        return
    await state.update_data(give_currency=give)
    await state.set_state(ExchangeFlow.choose_get)
    await call.message.edit_text(
        "Выберите валюту *Получите*:",
        reply_markup=kbd_choose_currency("get", exclude=give),
        parse_mode=ParseMode.MARKDOWN,
    )
    await call.answer()


@router.callback_query(F.data.startswith("get:"))
async def choose_get(call: CallbackQuery, state: FSMContext) -> None:
    get = call.data.split(":", 1)[1]
    if get not in CURRENCIES:
        await call.answer("Неизвестная валюта", show_alert=True)
        return
    data = await state.get_data()
    give = data.get("give_currency")
    if not give:
        await call.answer("Сначала выберите валюту 'Отдаёте'", show_alert=True)
        return
    if get == give:
        await call.answer("Валюты должны отличаться", show_alert=True)
        return
    await state.update_data(get_currency=get)
    await state.set_state(ExchangeFlow.choose_amount_mode)
    await call.message.edit_text("Какую сумму вы хотите ввести?", reply_markup=kbd_amount_mode())
    await call.answer()


@router.callback_query(F.data.startswith("mode:"))
async def choose_amount_mode(call: CallbackQuery, state: FSMContext) -> None:
    mode = call.data.split(":", 1)[1]
    if mode not in ("give", "get"):
        await call.answer("Неизвестный режим", show_alert=True)
        return
    await state.update_data(amount_mode=mode)
    await state.set_state(ExchangeFlow.enter_amount)
    if mode == "give":
        txt = "Введите сумму, которую вы *отдаёте* (числом):"
    else:
        txt = "Введите сумму, которую вы *хотите получить* (числом):"
    await call.message.edit_text(txt, parse_mode=ParseMode.MARKDOWN)
    await call.answer()


@router.message(ExchangeFlow.enter_amount)
async def enter_amount(message: Message, state: FSMContext) -> None:
    val = _parse_amount(message.text or "")
    if val is None:
        await message.answer("Не понял сумму. Введите число, например: 1500 или 1500.50")
        return
    await state.update_data(amount_value=val)
    await state.set_state(ExchangeFlow.enter_from_location)
    await message.answer("Укажите *страна/город отправления* (текстом):", parse_mode=ParseMode.MARKDOWN)


@router.message(ExchangeFlow.enter_from_location)
async def enter_from_location(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("Введите, пожалуйста, страна/город отправления текстом.")
        return
    await state.update_data(from_location=text)
    await state.set_state(ExchangeFlow.enter_to_location)
    await message.answer("Укажите *страна/город получения* (текстом):", parse_mode=ParseMode.MARKDOWN)


@router.message(ExchangeFlow.enter_to_location)
async def enter_to_location(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("Введите, пожалуйста, страна/город получения текстом.")
        return
    await state.update_data(to_location=text)
    await state.set_state(ExchangeFlow.waiting_for_calc)

    data = await state.get_data()
    give = data.get("give_currency")
    get = data.get("get_currency")
    mode = data.get("amount_mode")
    amount = data.get("amount_value")

    summary = (
        "Проверьте данные:\n"
        f"• Отдаёте: *{give}*\n"
        f"• Получите: *{get}*\n"
        f"• Режим: *{'ввожу сумму отдаю' if mode == 'give' else 'ввожу сумму получу'}*\n"
        f"• Сумма: *{amount}*\n"
        f"• Откуда: *{data.get('from_location')}*\n"
        f"• Куда: *{data.get('to_location')}*\n\n"
        "Нажмите *Показать курс* — мы посчитаем и предоставим вам результат."
    )
    await message.answer(summary, reply_markup=kbd_show_rate(), parse_mode=ParseMode.MARKDOWN)


@router.callback_query(ExchangeFlow.waiting_for_calc, F.data == "show_rate")
async def show_rate(
    call: CallbackQuery,
    state: FSMContext,
    config: Config,
    db_session_factory,
    rate_service: RateService,
) -> None:

    data = await state.get_data()
    give = data["give_currency"]
    get = data["get_currency"]
    mode = data["amount_mode"]
    amount = float(data["amount_value"])
    from_loc = data["from_location"]
    to_loc = data["to_location"]

    try:
        rr = await rate_service.get_rate(give, get)
    except Exception:
        await call.answer("Не удалось получить курс. Попробуйте позже.", show_alert=True)
        logging.exception("Rate fetch failed")
        return

    rate = round(rr.rate, 3)
    sources_text = _sources_to_text(rr.path)

    if mode == "give":
        give_amt = amount
        get_amt = amount * rr.rate
    else:
        get_amt = amount
        give_amt = amount / rr.rate

    give_out = _round_money_no_cents(give_amt)
    get_out = _round_money_no_cents(get_amt)

    # Create order record (stage calc)
    async with db_session_factory() as db:
        order = await create_order(
            db,
            user_id=call.from_user.id,
            give_currency=give,
            get_currency=get,
            amount_mode=mode,
            amount_value=amount,
            from_location=from_loc,
            to_location=to_loc,
        )
        await set_order_calc(
            db,
            order_id=order.id,
            rate=rate,
            calculated_give=float(give_out),
            calculated_get=float(get_out),
            sources=sources_text,
        )

    await state.update_data(order_id=order.id, rate=rate, give_out=give_out, get_out=get_out, sources=sources_text)

    # Notify admin about calculation (PLAIN TEXT, no Markdown)
    ulabel = _user_label(call.from_user)
    admin_text = (
        "🧮 Расчёт\n"
        f"👤 Пользователь: {ulabel}\n"
        f"🆔 Заказ: #{order.id}\n"
        f"💱 Пара: {give} → {get}\n"
        f"📌 Ввод: {'отдаю' if mode == 'give' else 'получу'} {amount}\n"
        f"📍 Откуда: {from_loc}\n"
        f"📍 Куда: {to_loc}\n"
        f"📈 Курс: 1 {give} = {rate:.3f} {get}\n"
        f"➡️ Отдам/получу: {give_out} {give} → {get_out} {get}\n"
        f"🔎 Источники: {sources_text or '—'}\n"
        f"⏱ AsOf (UTC): {rr.as_of.strftime('%Y-%m-%d %H:%M')}"
    )

    try:
        await call.bot.send_message(config.admin_id, admin_text)  # <-- без parse_mode
    except Exception:
        logging.exception("Failed to notify admin (calc)")

    # Show user (Markdown ok)
    user_text = (
        f"Курс: 1 {give} = *{rate:.2f}* {get}\n"
        f"Отдам/получу: *{give_out} {give}* → *{get_out} {get}*\n\n"
        "Теперь напишите ваш контакт (например @username или телефон)."
    )
    await call.message.edit_text(user_text, parse_mode=ParseMode.MARKDOWN)
    await state.set_state(ExchangeFlow.enter_contact)
    await call.answer()


@router.message(ExchangeFlow.enter_contact)
async def enter_contact(message: Message, state: FSMContext) -> None:
    contact = (message.text or "").strip()
    if len(contact) < 2:
        await message.answer("Введите контакт текстом.")
        return
    await state.update_data(contact=contact)
    await state.set_state(ExchangeFlow.waiting_for_submit)
    await message.answer("Готово. Нажмите *Отправить заявку*.", reply_markup=kbd_submit(), parse_mode=ParseMode.MARKDOWN)


@router.callback_query(ExchangeFlow.waiting_for_submit, F.data == "submit")
async def submit(call: CallbackQuery, state: FSMContext, config: Config, db_session_factory) -> None:

    data = await state.get_data()
    order_id = int(data["order_id"])
    contact = data.get("contact", "")

    give = data["give_currency"]
    get = data["get_currency"]
    mode = data["amount_mode"]
    amount = data["amount_value"]
    from_loc = data["from_location"]
    to_loc = data["to_location"]
    rate = float(data["rate"])
    give_out = int(data["give_out"])
    get_out = int(data["get_out"])
    sources_text = data.get("sources", "")

    async with db_session_factory() as db:
        await set_order_contact_and_submit(db, order_id=order_id, contact=contact)

    # Notify admin about submit (PLAIN TEXT, no Markdown)
    ulabel = _user_label(call.from_user)
    admin_text = (
        "🧾 Заявка\n"
        f"👤 Пользователь: {ulabel}\n"
        f"🆔 Заказ: #{order_id}\n"
        f"💱 Пара: {give} → {get}\n"
        f"📌 Ввод: {'отдаю' if mode == 'give' else 'получу'} {amount}\n"
        f"📍 Откуда: {from_loc}\n"
        f"📍 Куда: {to_loc}\n"
        f"📈 Курс: 1 {give} = {rate:.3f} {get}\n"
        f"➡️ Отдам/получу: {give_out} {give} → {get_out} {get}\n"
        f"📞 Контакт: {contact}\n"
        f"🔎 Источники: {sources_text or '—'}"
    )

    try:
        await call.bot.send_message(config.admin_id, admin_text)  # <-- без parse_mode
    except Exception:
        logging.exception("Failed to notify admin (submit)")

    await call.message.edit_text("Заявка отправлена. Администратор скоро с вами свяжется.")
    await state.clear()
    await call.answer("Отправлено")


@router.message(Command("export_users"))
async def cmd_export_users(message: Message, config: Config, db_session_factory) -> None:
    if message.from_user.id != config.admin_id:
        return
    async with db_session_factory() as db:
        content = await export_users_csv(db)

    file = BufferedInputFile(content, filename="users.csv")
    await message.answer_document(file, caption="Выгрузка подписчиков (users.csv)")


@router.callback_query(F.data == "back")
async def back(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.edit_text("Ок, вернулись в начало.", reply_markup=kbd_start())
    await call.answer()


async def main() -> None:
    cfg = load_config()

    logging.basicConfig(level=getattr(logging, cfg.log_level, logging.INFO))

    engine, session_factory = create_engine_and_sessionmaker(cfg.database_url)
    await init_db(engine)

    bot = Bot(token=cfg.bot_token)

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    # store shared dependencies
    dp["config"] = cfg
    dp["db_session_factory"] = session_factory
    dp["rate_service"] = RateService(ttl_seconds=cfg.rate_cache_ttl_seconds)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
