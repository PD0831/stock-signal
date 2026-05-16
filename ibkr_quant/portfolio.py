from __future__ import annotations

from datetime import date

import pandas as pd
import yfinance as yf

from .data import latest_close_on_or_before
from .models import TargetPosition
from .universe import nas100_members_on, qqq_market_cap_top5_on, qqq_top10_on


def rank_by_ma200_distance(
    histories: dict[str, pd.Series],
    as_of: date,
    candidates: tuple[str, ...],
    top_n: int = 5,
) -> list[str]:
    scores: list[tuple[str, float]] = []
    for symbol in candidates:
        history = histories.get(symbol)
        if history is None:
            continue
        eligible = history[history.index.date <= as_of]
        if len(eligible) < 200:
            continue
        ma200 = float(eligible.iloc[-200:].mean())
        if ma200 <= 0:
            continue
        scores.append((symbol, float(eligible.iloc[-1]) / ma200 - 1.0))
    scores.sort(key=lambda item: item[1], reverse=True)
    return [symbol for symbol, _ in scores[:top_n]]


def build_target_positions(histories: dict[str, pd.Series], as_of: date) -> list[TargetPosition]:
    members = list(nas100_members_on(as_of))

    # Fetch 300 calendar days of close + volume — enough for MA200 and 63-day ADV
    raw = yf.download(members, period="300d", interval="1d", auto_adjust=True, progress=False)
    closes = raw["Close"]
    volumes = raw["Volume"]

    # ADV: 63-day average dollar volume
    adv: dict[str, float] = {}
    for sym in members:
        if sym not in closes.columns:
            continue
        c = closes[sym].dropna().iloc[-63:]
        v = volumes[sym].dropna().iloc[-63:]
        idx = c.index.intersection(v.index)
        if len(idx) < 20:
            continue
        adv[sym] = float((c.loc[idx] * v.loc[idx]).mean())

    ranked_adv = sorted(adv, key=adv.__getitem__, reverse=True)

    # Sub-portfolio A — Stable Core: ADV Top 5 → 70%
    portfolio_a = ranked_adv[:5]
    weight_a = 0.70 / len(portfolio_a)

    # Sub-portfolio B — Aggressive: ADV Top 10 → MA200 Top 3 → 30%
    # Rank by distance above MA200 using the yfinance close data
    adv_top10 = ranked_adv[:10]
    ma200_scores: list[tuple[str, float]] = []
    for sym in adv_top10:
        if sym not in closes.columns:
            continue
        series = closes[sym].dropna()
        if len(series) < 200:
            continue
        ma200 = float(series.iloc[-200:].mean())
        last_close = float(series.iloc[-1])
        ma200_scores.append((sym, last_close / ma200 - 1.0))
    ma200_scores.sort(key=lambda x: x[1], reverse=True)
    portfolio_b = [sym for sym, _ in ma200_scores[:3]]
    weight_b = 0.30 / len(portfolio_b) if portfolio_b else 0.0

    # Merge weights
    weights: dict[str, float] = {}
    sources: dict[str, list[str]] = {}
    for sym in portfolio_a:
        weights[sym] = weights.get(sym, 0.0) + weight_a
        sources.setdefault(sym, []).append("adv_top5")
    for sym in portfolio_b:
        weights[sym] = weights.get(sym, 0.0) + weight_b
        sources.setdefault(sym, []).append("ma200_top3")

    # Cap each position at 25%, redistribute excess proportionally
    cap = 0.25
    for _ in range(10):
        over = {s: w - cap for s, w in weights.items() if w > cap}
        if not over:
            break
        total_excess = sum(over.values())
        uncapped = [s for s, w in weights.items() if w <= cap]
        per_uncapped = total_excess / len(uncapped) if uncapped else 0.0
        for sym in over:
            weights[sym] = cap
        for sym in uncapped:
            weights[sym] = min(cap, weights[sym] + per_uncapped)

    return [
        TargetPosition(symbol=sym, weight=round(w, 6), source="+".join(sources[sym]))
        for sym, w in sorted(weights.items())
    ]


def reference_prices(histories: dict[str, pd.Series], as_of: date, symbols: list[str]) -> dict[str, float]:
    prices: dict[str, float] = {}
    for symbol in symbols:
        history = histories.get(symbol)
        if history is None:
            continue
        price = latest_close_on_or_before(history, as_of)
        if price is not None:
            prices[symbol] = price
    return prices

