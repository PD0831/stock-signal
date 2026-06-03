"""Calibrate the latest MA200 breadth count to Finviz.

Python imports usercustomize after sitecustomize. The existing sitecustomize
patch handles the SPY holdings universe and Yahoo price download; this wrapper
only adjusts the latest MA200 count to match Finviz's S&P 500 / price above
SMA200 screener, which is the external reference used for the live chart.
"""
from __future__ import annotations

import importlib.abc
import re
import sys
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

FINVIZ_SMA200_URL = "https://finviz.com/screener.ashx"


def _fetch_finviz_sma200_symbols() -> list[str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    symbols: list[str] = []
    for start in range(1, 521, 20):
        params = {"v": "111", "f": "idx_sp500,ta_sma200_pa", "ft": "3", "r": str(start)}
        url = f"{FINVIZ_SMA200_URL}?{urlencode(params)}"
        with urlopen(Request(url, headers=headers), timeout=30) as response:
            html = response.read().decode("utf-8", "ignore")
        page_symbols = re.findall(
            r'<a href="stock\?t=([A-Z0-9.\-]+)&ty=c&p=d&b=1" class="tab-link">\1</a>',
            html,
        )
        if not page_symbols:
            break
        symbols.extend(symbol.replace(".", "-") for symbol in page_symbols)
        if len(page_symbols) < 20:
            break
    return sorted(dict.fromkeys(symbols))


def _recalculate_derived_fields(record: dict[str, Any]) -> None:
    a20 = record.get("a20")
    a50 = record.get("a50")
    a200 = record.get("a200")
    if a20 is None or a50 is None or a200 is None:
        return
    values = [float(a20), float(a50), float(a200)]
    fast_values = [float(a20), float(a50)]
    record["s"] = round(min(values), 2)
    record["bd"] = round(100 - max(values), 2)
    record["pb"] = round(min(fast_values) - min(values), 2)
    record["rc"] = round(max(values) - max(fast_values), 2)


def _apply_finviz_calibration(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return payload
    try:
        universe_symbols = set()
        n_stocks = int(payload.get("n_stocks") or 0)
        finviz_symbols = _fetch_finviz_sma200_symbols()
        if not finviz_symbols or not n_stocks:
            return payload
        count = len(finviz_symbols)
        pct = round(count / n_stocks * 100, 2)

        def apply(record: dict[str, Any] | None) -> None:
            if not isinstance(record, dict):
                return
            record["a200"] = pct
            record["a200_n"] = count
            record["valid_200_n"] = n_stocks
            _recalculate_derived_fields(record)

        daily_close = payload.get("daily_close")
        if isinstance(daily_close, dict):
            apply(daily_close.get("current"))
        records = payload.get("records")
        if isinstance(records, list) and records:
            apply(records[-1])

        payload["ma200_calibration_source"] = "finviz_idx_sp500_ta_sma200_pa"
        payload["finviz_above_ma200"] = count
        payload["finviz_above_ma200_symbols"] = finviz_symbols
        payload["ma_policy"] = (
            "Latest MA200 count is calibrated to Finviz idx_sp500,ta_sma200_pa; "
            "historical bars use Yahoo regular Close SMA"
        )
    except Exception as exc:
        payload["ma200_calibration_error"] = str(exc)
    return payload


def _install_patch(module: Any) -> None:
    if getattr(module, "_FINVIZ_MA200_CALIBRATION_PATCHED", False):
        return
    original = module.compute_breadth_data

    def compute_breadth_data_with_finviz_calibration():
        return _apply_finviz_calibration(original())

    module.compute_breadth_data = compute_breadth_data_with_finviz_calibration
    module._FINVIZ_MA200_CALIBRATION_PATCHED = True


class _PatchLoader(importlib.abc.Loader):
    def __init__(self, wrapped: importlib.abc.Loader) -> None:
        self.wrapped = wrapped

    def create_module(self, spec):
        create_module = getattr(self.wrapped, "create_module", None)
        return None if create_module is None else create_module(spec)

    def exec_module(self, module) -> None:
        self.wrapped.exec_module(module)
        _install_patch(module)


class _PatchFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname != "live_stock_signal_app":
            return None
        for finder in sys.meta_path:
            if finder is self:
                continue
            spec = finder.find_spec(fullname, path, target) if hasattr(finder, "find_spec") else None
            if spec and isinstance(spec.loader, importlib.abc.Loader):
                spec.loader = _PatchLoader(spec.loader)
                return spec
        return None


if "live_stock_signal_app" in sys.modules:
    _install_patch(sys.modules["live_stock_signal_app"])
else:
    sys.meta_path.insert(0, _PatchFinder())
