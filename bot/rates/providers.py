from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import aiohttp
from lxml import etree


@dataclass(frozen=True)
class CbrRates:
    eur_rub: float
    usd_rub: float
    as_of: datetime


@dataclass(frozen=True)
class NbuRates:
    eur_uah: float
    usd_uah: float
    as_of: datetime


@dataclass(frozen=True)
class BinanceRates:
    eur_usdt: float          # USDT per 1 EUR (symbol EURUSDT)
    usdt_uah: float          # UAH per 1 USDT (symbol USDTUAH)
    usdt_usd: float          # USD per 1 USDT (symbol USDTUSD)
    as_of: datetime


async def fetch_cbr(session: aiohttp.ClientSession) -> CbrRates:
    """CBR daily rates XML.
    Endpoint: https://www.cbr.ru/scripts/XML_daily.asp
    """
    url = "https://www.cbr.ru/scripts/XML_daily.asp"
    async with session.get(url, timeout=20) as resp:
        resp.raise_for_status()
        raw = await resp.read()

    # XML is usually windows-1251
    parser = etree.XMLParser(recover=True, encoding="windows-1251")
    root = etree.fromstring(raw, parser=parser)

    def get_rate(char_code: str) -> float:
        for valute in root.findall("Valute"):
            cc = (valute.findtext("CharCode") or "").strip()
            if cc == char_code:
                nominal = float((valute.findtext("Nominal") or "1").strip())
                value_txt = (valute.findtext("Value") or "").strip().replace(",", ".")
                value = float(value_txt)
                return value / nominal
        raise RuntimeError(f"CBR: currency not found: {char_code}")

    eur_rub = get_rate("EUR")
    usd_rub = get_rate("USD")
    return CbrRates(eur_rub=eur_rub, usd_rub=usd_rub, as_of=datetime.now(timezone.utc))


async def fetch_nbu(session: aiohttp.ClientSession) -> NbuRates:
    """NBU official rates JSON.
    Endpoint: https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json
    """
    url = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json"
    async with session.get(url, timeout=20) as resp:
        resp.raise_for_status()
        data = await resp.json(content_type=None)

    def find(code: str) -> float:
        for item in data:
            if (item.get("cc") or "").upper() == code:
                return float(item.get("rate"))
        raise RuntimeError(f"NBU: currency not found: {code}")

    eur_uah = find("EUR")
    usd_uah = find("USD")
    return NbuRates(eur_uah=eur_uah, usd_uah=usd_uah, as_of=datetime.now(timezone.utc))


async def fetch_binance(session: aiohttp.ClientSession) -> BinanceRates:
    """Binance public price ticker.
    Docs: GET /api/v3/ticker/price
    """
    base = "https://api.binance.com/api/v3/ticker/price"

    async def price(symbol: str) -> float:
        async with session.get(base, params={"symbol": symbol}, timeout=20) as resp:
            resp.raise_for_status()
            payload: dict[str, Any] = await resp.json()
            return float(payload["price"])

    # EURUSDT: USDT per 1 EUR
    eur_usdt = await price("EURUSDT")
    # USDTUAH: UAH per 1 USDT
    usdt_uah = await price("USDTUAH")
    # USDTUSD: USD per 1 USDT
    usdt_usd = await price("USDTUSD")

    return BinanceRates(eur_usdt=eur_usdt, usdt_uah=usdt_uah, usdt_usd=usdt_usd, as_of=datetime.now(timezone.utc))
