from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

import aiohttp

from .providers import BinanceRates, CbrRates, NbuRates, fetch_binance, fetch_cbr, fetch_nbu


@dataclass(frozen=True)
class RateResult:
    rate: float
    path: List[Tuple[str, str, str]]  # (from,to,source)
    as_of: datetime


class RateService:
    def __init__(self, ttl_seconds: int = 600):
        self.ttl = timedelta(seconds=ttl_seconds)
        self._cache: dict[str, tuple[datetime, RateResult]] = {}
        self._last_sources_as_of: datetime | None = None

    async def get_rate(self, frm: str, to: str) -> RateResult:
        frm = frm.upper()
        to = to.upper()
        key = f"{frm}->{to}"
        now = datetime.now(timezone.utc)
        cached = self._cache.get(key)
        if cached and cached[0] > now:
            return cached[1]

        # Refresh base rates (CBR+NBU+Binance) once per call; inexpensive for small bot
        async with aiohttp.ClientSession(headers={"User-Agent": "u2c-exchange-bot/1.0"}) as session:
            cbr, nbu, bnc = await self._fetch_all(session)

        graph = self._build_graph(cbr, nbu, bnc)
        rate, path, as_of = self._find_rate(graph, frm, to, now)
        result = RateResult(rate=rate, path=path, as_of=as_of)
        self._cache[key] = (now + self.ttl, result)
        return result

    async def _fetch_all(self, session: aiohttp.ClientSession) -> tuple[CbrRates, NbuRates, BinanceRates]:
        # run sequentially to keep it simple and predictable
        cbr = await fetch_cbr(session)
        nbu = await fetch_nbu(session)
        bnc = await fetch_binance(session)
        # as_of: latest of sources
        self._last_sources_as_of = max(cbr.as_of, nbu.as_of, bnc.as_of)
        return cbr, nbu, bnc

    def _build_graph(self, cbr: CbrRates, nbu: NbuRates, bnc: BinanceRates) -> Dict[str, List[Tuple[str, float, str]]]:
        """Directed graph: from -> [(to, rate, source)]
        rate means: amount_to = amount_from * rate
        """
        g: Dict[str, List[Tuple[str, float, str]]] = {}

        def add_edge(a: str, b: str, r: float, src: str):
            g.setdefault(a, []).append((b, r, src))

        # CBR (official)
        add_edge("EUR", "RUB", cbr.eur_rub, "CBR")
        add_edge("RUB", "EUR", 1.0 / cbr.eur_rub, "CBR")

        add_edge("USD", "RUB", cbr.usd_rub, "CBR")
        add_edge("RUB", "USD", 1.0 / cbr.usd_rub, "CBR")

        # NBU (official)
        add_edge("EUR", "UAH", nbu.eur_uah, "NBU")
        add_edge("UAH", "EUR", 1.0 / nbu.eur_uah, "NBU")

        add_edge("USD", "UAH", nbu.usd_uah, "NBU")
        add_edge("UAH", "USD", 1.0 / nbu.usd_uah, "NBU")

        # Derived UAH<->RUB using EUR as bridge (still official sources)
        uah_rub = cbr.eur_rub / nbu.eur_uah  # RUB per 1 UAH
        add_edge("UAH", "RUB", uah_rub, "CBR+NBU")
        add_edge("RUB", "UAH", 1.0 / uah_rub, "CBR+NBU")

        # Binance spot public prices for USDT crosses
        # EURUSDT: USDT per 1 EUR
        add_edge("EUR", "USDT", bnc.eur_usdt, "Binance")
        add_edge("USDT", "EUR", 1.0 / bnc.eur_usdt, "Binance")

        # USDTUAH: UAH per 1 USDT
        add_edge("USDT", "UAH", bnc.usdt_uah, "Binance")
        add_edge("UAH", "USDT", 1.0 / bnc.usdt_uah, "Binance")

        # USDTUSD: USD per 1 USDT
        add_edge("USDT", "USD", bnc.usdt_usd, "Binance")
        add_edge("USD", "USDT", 1.0 / bnc.usdt_usd, "Binance")

        return g

    def _find_rate(
        self,
        graph: Dict[str, List[Tuple[str, float, str]]],
        frm: str,
        to: str,
        now: datetime,
    ) -> tuple[float, List[Tuple[str, str, str]], datetime]:
        if frm == to:
            return 1.0, [], self._last_sources_as_of or now

        # BFS over small graph with path multiplication
        from collections import deque

        q = deque()
        q.append(frm)
        prev: dict[str, tuple[str, float, str]] = {}
        visited = set([frm])

        while q:
            cur = q.popleft()
            for nxt, r, src in graph.get(cur, []):
                if nxt in visited:
                    continue
                visited.add(nxt)
                prev[nxt] = (cur, r, src)
                if nxt == to:
                    q.clear()
                    break
                q.append(nxt)

        if to not in prev:
            raise RuntimeError(f"No conversion path from {frm} to {to}")

        # reconstruct
        path_edges: List[Tuple[str, str, str]] = []
        rate = 1.0
        cur = to
        while cur != frm:
            p, r, src = prev[cur]
            path_edges.append((p, cur, src))
            rate *= r
            cur = p
        path_edges.reverse()

        as_of = self._last_sources_as_of or now
        return rate, path_edges, as_of
