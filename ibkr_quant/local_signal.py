from __future__ import annotations

from datetime import date, datetime, time, timezone
from pathlib import Path

import yfinance as yf

from .breadth import BreadthComputer
from .config import AppConfig
from .models import SignalDecision, SignalSnapshot, SignalType
from .signals import SignalParams, calculate_decision


def compute_local_decision(config: AppConfig, params: SignalParams | None = None) -> SignalDecision:
    # VIX / VIX3M via yfinance
    vix_raw = yf.download(["^VIX", "^VIX3M"], period="5d", interval="1d",
                           auto_adjust=False, progress=False)["Close"]
    vix_val = float(vix_raw["^VIX"].dropna().iloc[-1])
    vix3m_val = float(vix_raw["^VIX3M"].dropna().iloc[-1])

    # SP500 breadth via incremental EMA state
    computer = BreadthComputer(config.ema_state_path)
    breadth = computer.update(date.today())

    ts = datetime.combine(breadth.date, time(21, 5), tzinfo=timezone.utc)
    base = dict(
        timestamp=ts,
        nas100_close=None,
        vix=vix_val,
        vix3m=vix3m_val,
        s5th=breadth.s5th,
        s5fi=breadth.s5fi,
        s5tw=breadth.s5tw,
        previous_s5th=breadth.previous_s5th,
        previous_s5fi=breadth.previous_s5fi,
        previous_s5tw=breadth.previous_s5tw,
    )

    probes = {
        SignalType.SHORT: calculate_decision(SignalSnapshot(signal=SignalType.SHORT, **base), params),
        SignalType.LONG: calculate_decision(SignalSnapshot(signal=SignalType.LONG, **base), params),
        SignalType.MEAN: calculate_decision(SignalSnapshot(signal=SignalType.MEAN, **base), params),
    }
    if probes[SignalType.SHORT].short_signal:
        return probes[SignalType.SHORT]
    if probes[SignalType.LONG].long_signal:
        return probes[SignalType.LONG]
    if config.enable_mean and probes[SignalType.MEAN].mean_signal:
        return probes[SignalType.MEAN]

    neutral = probes[SignalType.LONG]
    neutral.accepted = False
    neutral.confirmed_signal = None
    neutral.reason = "local recomputation produced no actionable signal"
    return neutral
