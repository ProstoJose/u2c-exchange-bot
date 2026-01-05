from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

CURRENCIES = ["USD", "EUR", "UAH", "RUB", "USDT"]


def kbd_start() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Начать расчёт", callback_data="start_calc")],
    ])


def kbd_choose_currency(prefix: str, exclude: str | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for c in CURRENCIES:
        if exclude and c == exclude:
            continue
        row.append(InlineKeyboardButton(text=c, callback_data=f"{prefix}:{c}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kbd_amount_mode() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Хочу обменять (введу сумму ОТДАЮ)", callback_data="mode:give"),
        ],
        [
            InlineKeyboardButton(text="Хочу получить (введу сумму ПОЛУЧУ)", callback_data="mode:get"),
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")],
    ])


def kbd_show_rate() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Показать курс", callback_data="show_rate")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")],
    ])


def kbd_submit() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отправить заявку", callback_data="submit")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")],
    ])
