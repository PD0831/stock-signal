"""Runtime patches for the live breadth app.

Python imports this module automatically during interpreter startup when the
repository root is on sys.path. The patch keeps market breadth on the SPY
holdings constituent-security ticker denominator, with GOOG and GOOGL counted
separately.

Breadth uses regular Close prices, not dividend-adjusted prices.
"""
from __future__ import annotations

import gc
import importlib.abc
import sys
from datetime import datetime
from typing import Any

BREADTH_DAILY_PERIOD = "2y"


def _load_spy_universe(app: Any) -> tuple[list[str], dict[str, Any]]:
    try:
        from scripts.spy_universe import download_spy_universe
    except ModuleNotFoundError:
        from spy_universe import download_spy_universe

    try:
        universe = download_spy_universe()
        diagnostics = {
            "universe_source": "spdr_spy_holdings_xlsx",
            "spy_holdings_as_of": universe.as_of,
            "spy_raw_holding_rows": universe.raw_holding_rows,
            "spy_excluded_rows": universe.excluded_rows,
            "spy_excluded_count": universe.excluded_count,
        }
        return universe.symbols, diagnostics
    except Exception as exc:
        symbols = app.fetch_current_symbols("sp500")
        return symbols, {
            "universe_source": "fallback_sp500_wikipedia",
            "universe_error": str(exc),
            "spy_raw_holding_rows": None,
            "spy_excluded_rows": [],
            "spy_excluded_count": None,
        }


def _install_breadth_patch(app: Any) -> None:
    if getattr(app, "_FIXED_TICKER_BREADTH_PATCHED", False):
        return

    pd = app.pd
    np = app.np

    def pct_above(prices, ref, min_n: int, denominator: int | None = None):
        valid = prices.notna() & ref.notna()
        above = (prices > ref) & valid
        n_valid = valid.sum(axis=1)
        n_above = above.sum(axis=1).astype(float)
        denom = denominator if denominator and denominator > 0 else prices.shape[1]
        pct = n_above / max(denom, 1) * 100
        pct[n_valid < min_n] = np.nan
        return pct

    def count_above(prices, ref, min_n: int) -> Any:
        valid = prices.notna() & ref.notna()
        above = (prices > ref) & valid
        n_valid = valid.sum(axis=1)
        counts = above.sum(axis=1).astype(float)
        counts[n_valid < min_n] = np.nan
        return counts

    def valid_count(prices, ref) -> Any:
        return (prices.notna() & ref.notna()).sum(axis=1).astype(float)

    def calculate_breadth_from_daily(daily, min_n: int = app.BREADTH_MIN_STOCKS, denominator: int | None = None):
        ma20_ts = daily.rolling(20, min_periods=20).mean()
        ma50_ts = daily.rolling(50, min_periods=50).mean()
        ma200_ts = daily.rolling(200, min_periods=200).mean()
        above_20 = pct_above(daily, ma20_ts, min_n, denominator=denominator)
        above_50 = pct_above(daily, ma50_ts, min_n, denominator=denominator)
        above_200 = pct_above(daily, ma200_ts, min_n, denominator=denominator)
        m = pd.concat([above_20, above_50, above_200], axis=1)
        m2 = pd.concat([above_20, above_50], axis=1)
        out = pd.DataFrame({
            "above_20": above_20.round(2),
            "above_50": above_50.round(2),
            "above_200": above_200.round(2),
            "above_20_n": count_above(daily, ma20_ts, min_n),
            "above_50_n": count_above(daily, ma50_ts, min_n),
            "above_200_n": count_above(daily, ma200_ts, min_n),
            "valid_20_n": valid_count(daily, ma20_ts),
            "valid_50_n": valid_count(daily, ma50_ts),
            "valid_200_n": valid_count(daily, ma200_ts),
            "strong": m.min(axis=1).round(2),
            "breakdown": (100 - m.max(axis=1)).round(2),
            "pullback": (m2.min(axis=1) - m.min(axis=1)).round(2),
            "recovery": (m.max(axis=1) - m2.max(axis=1)).round(2),
        }, index=daily.index)
        out["momentum"] = app._calc_momentum(out).values
        return out

    def calculate_breadth(daily, hourly, denominator: int | None = None):
        common = daily.columns.intersection(hourly.columns)
        ma20_ts = daily[common].rolling(20, min_periods=20).mean()
        ma50_ts = daily[common].rolling(50, min_periods=50).mean()
        ma200_ts = daily[common].rolling(200, min_periods=200).mean()
        ma20_ref = app._daily_to_hourly_ref(ma20_ts, hourly.index)
        ma50_ref = app._daily_to_hourly_ref(ma50_ts, hourly.index)
        ma200_ref = app._daily_to_hourly_ref(ma200_ts, hourly.index)
        h = hourly[common]
        above_20 = app._ema(pct_above(h, ma20_ref[common], app.BREADTH_MIN_STOCKS, denominator), app.BREADTH_SMOOTH)
        above_50 = app._ema(pct_above(h, ma50_ref[common], app.BREADTH_MIN_STOCKS, denominator), app.BREADTH_SMOOTH)
        above_200 = app._ema(pct_above(h, ma200_ref[common], app.BREADTH_MIN_STOCKS, denominator), app.BREADTH_SMOOTH)
        m = pd.concat([above_20, above_50, above_200], axis=1)
        m2 = pd.concat([above_20, above_50], axis=1)
        return pd.DataFrame({
            "above_20": above_20.round(2),
            "above_50": above_50.round(2),
            "above_200": above_200.round(2),
            "above_20_n": count_above(h, ma20_ref[common], app.BREADTH_MIN_STOCKS),
            "above_50_n": count_above(h, ma50_ref[common], app.BREADTH_MIN_STOCKS),
            "above_200_n": count_above(h, ma200_ref[common], app.BREADTH_MIN_STOCKS),
            "strong": m.min(axis=1).round(2),
            "breakdown": (100 - m.max(axis=1)).round(2),
            "pullback": (m2.min(axis=1) - m.min(axis=1)).round(2),
            "recovery": (m.max(axis=1) - m2.max(axis=1)).round(2),
        }, index=hourly.index)

    def close_columns_from_download(frame, symbols: list[str]):
        if frame.empty:
            return pd.DataFrame()
        if not isinstance(frame.columns, pd.MultiIndex):
            if len(symbols) == 1 and "Close" in frame.columns:
                return frame[["Close"]].rename(columns={"Close": symbols[0]})
            return frame

        level0 = {str(x) for x in frame.columns.get_level_values(0)}
        closes = {}
        for symbol in symbols:
            try:
                if symbol in level0:
                    sub = frame[symbol]
                    if "Close" in sub.columns:
                        closes[symbol] = sub["Close"]
                else:
                    sub = frame.xs(symbol, axis=1, level=1)
                    if "Close" in sub.columns:
                        closes[symbol] = sub["Close"]
            except Exception:
                continue
        return pd.DataFrame(closes)

    def download_daily_closes(symbols: list[str]):
        frames = []
        for i in range(0, len(symbols), app._YF_BATCH_SIZE):
            batch = symbols[i:i + app._YF_BATCH_SIZE]
            raw = app.yf.download(
                batch,
                period=BREADTH_DAILY_PERIOD,
                interval="1d",
                group_by="ticker",
                auto_adjust=False,
                progress=False,
                threads=True,
            )
            closes = close_columns_from_download(raw, batch)
            if not closes.empty:
                frames.append(closes.astype("float32"))
            del raw
            gc.collect()
        if not frames:
            return pd.DataFrame()
        daily = pd.concat(frames, axis=1)
        daily = daily.loc[:, ~daily.columns.duplicated()]
        idx = pd.DatetimeIndex(daily.index)
        if idx.tz is not None:
            idx = idx.tz_convert("America/New_York").tz_localize(None)
        daily.index = pd.DatetimeIndex(idx).normalize()
        return daily.sort_index()

    def download_hourly_closes(symbols: list[str]):
        frames = []
        for i in range(0, len(symbols), app._YF_BATCH_SIZE):
            batch = symbols[i:i + app._YF_BATCH_SIZE]
            raw = app.yf.download(
                batch,
                period=app.BREADTH_PERIOD,
                interval="1h",
                group_by="ticker",
                auto_adjust=False,
                progress=False,
                threads=True,
            )
            closes = close_columns_from_download(raw, batch)
            if not closes.empty:
                frames.append(closes.astype("float32"))
            del raw
            gc.collect()
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, axis=1)

    def record_from_breadth_row(ts: Any, row: Any, label: str | None = None):
        def v(x: Any) -> float | None:
            return None if pd.isna(x) else round(float(x), 2)

        def n(x: Any) -> int | None:
            return None if pd.isna(x) else int(round(float(x)))

        if label is None:
            label = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)
        return {"t": label,
                "s": v(row["strong"]), "bd": v(row["breakdown"]),
                "pb": v(row["pullback"]), "rc": v(row["recovery"]),
                "mid": v(row.get("ntss")), "mom": v(row.get("momentum")),
                "a20": v(row.get("above_20")),
                "a50": v(row.get("above_50")),
                "a200": v(row.get("above_200")),
                "a20_n": n(row.get("above_20_n")),
                "a50_n": n(row.get("above_50_n")),
                "a200_n": n(row.get("above_200_n")),
                "valid_20_n": n(row.get("valid_20_n")),
                "valid_50_n": n(row.get("valid_50_n")),
                "valid_200_n": n(row.get("valid_200_n"))}

    def daily_close_payload(daily_df, ntss=None, min_n: int = app.BREADTH_MIN_STOCKS, universe_denominator: int | None = None):
        daily_breadth = calculate_breadth_from_daily(daily_df, min_n=min_n, denominator=universe_denominator)
        if ntss is not None and not ntss.empty:
            idx = pd.DatetimeIndex(daily_breadth.index)
            if idx.tz is not None:
                idx = idx.tz_convert("America/New_York").tz_localize(None)
            daily_breadth.index = pd.DatetimeIndex(idx).normalize()
            ntss = ntss.dropna().sort_index()
            if ntss.empty:
                return None
            latest_ntss_day = ntss.index[-1]
            daily_breadth = daily_breadth.loc[daily_breadth.index <= latest_ntss_day]
            daily_breadth["ntss"] = ntss.reindex(daily_breadth.index, method="ffill").values
        valid = daily_breadth.dropna(subset=["strong", "breakdown"], how="any")
        if valid.empty:
            return None
        current = valid.iloc[-1]
        previous = valid.iloc[-2] if len(valid) >= 2 else None
        current_ts = valid.index[-1]
        previous_ts = valid.index[-2] if previous is not None else None
        payload = {"current": record_from_breadth_row(current_ts, current, f"{current_ts:%Y-%m-%d} EOD")}
        if previous is not None and previous_ts is not None:
            payload["previous"] = record_from_breadth_row(previous_ts, previous, f"{previous_ts:%Y-%m-%d} EOD")
        return payload

    def compute_breadth_data():
        print("[breadth] starting computation with SPY holdings, raw Close, fixed denominator...")
        symbols, universe_meta = _load_spy_universe(app)
        universe_denominator = len(symbols)

        daily_df = download_daily_closes(symbols)

        print(f"[breadth] downloading {len(symbols)} tickers hourly in batches...")
        hourly_df = download_hourly_closes(symbols)
        hourly_df = hourly_df.loc[:, hourly_df.isna().mean() < 0.5]
        if hourly_df.index.tz is None:
            hourly_df.index = hourly_df.index.tz_localize("UTC")

        breadth = calculate_breadth(daily_df, hourly_df, denominator=universe_denominator)
        daily_close = daily_close_payload(daily_df, app._download_daily_ntss(), universe_denominator=universe_denominator)

        vix_frames = {}
        for ticker, key in [("^VIX", "vix"), ("^VIX3M", "vix3m")]:
            try:
                hist = app.yf.Ticker(ticker).history(period=app.BREADTH_PERIOD, interval="1h")
                if not hist.empty:
                    vix_frames[key] = hist["Close"].rename(key)
            except Exception:
                pass
        vix_df = pd.concat(vix_frames.values(), axis=1) if vix_frames else pd.DataFrame()
        ntss = app._calc_ntss(vix_df, breadth.index)

        breadth["ntss"] = ntss.values
        breadth["momentum"] = app._calc_momentum(breadth).values

        try:
            idx_et = breadth.index.tz_convert("America/New_York")
        except Exception:
            idx_et = breadth.index

        records = [
            record_from_breadth_row(idx_et[i], row, app.format_breadth_bar_time(idx_et[i]))
            for i, (_, row) in enumerate(breadth.iterrows())
        ]
        print(f"[breadth] done - {len(records)} bars")
        return {"generated_at": datetime.now().isoformat(timespec="seconds"),
                "timeframe": "1H",
                "n_stocks": universe_denominator,
                "n_valid_daily": daily_df.shape[1],
                "n_valid_hourly": hourly_df.shape[1],
                "price_basis": "regular_close_not_dividend_adjusted",
                "ma_policy": "SMA uses exact 20/50/200 completed daily closes",
                "counting_method": "constituent_security_ticker",
                "share_class_policy": "GOOG and GOOGL counted separately",
                "daily_close": daily_close,
                "previous_day_close": app.previous_day_close_record(records),
                "records": records,
                **universe_meta}

    app._pct_above = pct_above
    app._calculate_breadth_from_daily = calculate_breadth_from_daily
    app._calculate_breadth = calculate_breadth
    app.daily_close_payload = daily_close_payload
    app.compute_breadth_data = compute_breadth_data
    app._FIXED_TICKER_BREADTH_PATCHED = True


class _LiveAppPatchLoader(importlib.abc.Loader):
    def __init__(self, wrapped: importlib.abc.Loader) -> None:
        self.wrapped = wrapped

    def create_module(self, spec):
        create_module = getattr(self.wrapped, "create_module", None)
        if create_module is None:
            return None
        return create_module(spec)

    def exec_module(self, module) -> None:
        self.wrapped.exec_module(module)
        _install_breadth_patch(module)


class _LiveAppPatchFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname != "live_stock_signal_app":
            return None
        for finder in sys.meta_path:
            if finder is self:
                continue
            spec = finder.find_spec(fullname, path, target) if hasattr(finder, "find_spec") else None
            if spec and isinstance(spec.loader, importlib.abc.Loader):
                spec.loader = _LiveAppPatchLoader(spec.loader)
                return spec
        return None


if "live_stock_signal_app" in sys.modules:
    _install_breadth_patch(sys.modules["live_stock_signal_app"])
else:
    sys.meta_path.insert(0, _LiveAppPatchFinder())
