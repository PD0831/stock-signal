from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd

import live_stock_signal_app as app
from scripts import fetch_stock_data


class StockUniverseTests(unittest.TestCase):
    def test_symbol_normalization_keeps_alphabet_share_classes_separate(self) -> None:
        frame = pd.DataFrame({"Symbol": ["GOOG", "GOOGL", "BRK.B", "BRK-B", "GOOG"]})

        symbols = fetch_stock_data._symbols_from_column(frame, "Symbol")

        self.assertEqual(symbols.count("GOOG"), 1)
        self.assertEqual(symbols.count("GOOGL"), 1)
        self.assertIn("BRK-B", symbols)
        self.assertEqual(len(symbols), 3)

    def test_fetch_stock_data_drops_current_session_before_data_ready_time(self) -> None:
        frame = pd.DataFrame({
            "symbol": ["AAA", "AAA"],
            "date": [pd.Timestamp("2026-06-02").date(), pd.Timestamp("2026-06-03").date()],
            "close": [10.0, 11.0],
        })
        now = datetime(2026, 6, 3, 14, 25, tzinfo=ZoneInfo("America/New_York"))

        filtered = fetch_stock_data.drop_unfinished_current_session(frame, now=now)

        self.assertEqual(filtered["date"].tolist(), [pd.Timestamp("2026-06-02").date()])

    def test_fetch_stock_data_keeps_current_session_after_data_ready_time(self) -> None:
        frame = pd.DataFrame({
            "symbol": ["AAA", "AAA"],
            "date": [pd.Timestamp("2026-06-02").date(), pd.Timestamp("2026-06-03").date()],
            "close": [10.0, 11.0],
        })
        now = datetime(2026, 6, 3, 16, 16, tzinfo=ZoneInfo("America/New_York"))

        filtered = fetch_stock_data.drop_unfinished_current_session(frame, now=now)

        self.assertEqual(filtered["date"].tolist(), frame["date"].tolist())


class CacheTests(unittest.TestCase):
    def setUp(self) -> None:
        app._memory_cache.clear()

    def test_cache_get_deletes_expired_items(self) -> None:
        app._memory_cache["old"] = (
            datetime.now(timezone.utc) - timedelta(minutes=10),
            {"large": "payload"},
        )

        self.assertIsNone(app.cache_get("old", ttl_minutes=1))
        self.assertNotIn("old", app._memory_cache)

    def test_cache_set_evicts_least_recently_used_items(self) -> None:
        for idx in range(app._CACHE_MAX_ITEMS + 1):
            app.cache_set(f"k{idx}", idx)

        self.assertEqual(len(app._memory_cache), app._CACHE_MAX_ITEMS)
        self.assertNotIn("k0", app._memory_cache)
        self.assertIn(f"k{app._CACHE_MAX_ITEMS}", app._memory_cache)


class DownloadBatchingTests(unittest.TestCase):
    def setUp(self) -> None:
        app._memory_cache.clear()

    def _fake_download_frame(self, symbols: list[str]) -> pd.DataFrame:
        idx = pd.date_range("2025-01-01", periods=2)
        cols = pd.MultiIndex.from_product([symbols, ["Close", "Volume"]])
        data = []
        for _ in idx:
            row = []
            for _symbol in symbols:
                row.extend([100.0, 1_000_000.0])
            data.append(row)
        return pd.DataFrame(data, index=idx, columns=cols)

    def test_fetch_history_uses_bounded_key_and_batches_downloads(self) -> None:
        symbols = [f"S{i:03d}" for i in range(app._HISTORY_BATCH + 3)]
        calls: list[list[str]] = []

        def fake_download(batch: list[str], **_kwargs) -> pd.DataFrame:
            calls.append(batch)
            return self._fake_download_frame(batch)

        with patch.object(app.yf, "download", side_effect=fake_download):
            app.fetch_history(symbols)

        self.assertEqual([len(c) for c in calls], [app._HISTORY_BATCH, 3])
        [cache_key] = list(app._memory_cache.keys())
        self.assertLess(len(cache_key), 80)
        self.assertNotIn(",".join(symbols), cache_key)

    def test_download_hourly_closes_batches_downloads(self) -> None:
        symbols = [f"S{i:03d}" for i in range(app._YF_BATCH_SIZE + 2)]
        calls: list[list[str]] = []

        def fake_download(batch: list[str], **_kwargs) -> pd.DataFrame:
            calls.append(batch)
            return self._fake_download_frame(batch)

        with patch.object(app.yf, "download", side_effect=fake_download):
            hourly = app._download_hourly_closes(symbols)

        self.assertEqual([len(c) for c in calls], [app._YF_BATCH_SIZE, 2])
        self.assertEqual(hourly.shape[1], len(symbols))


class SignalSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        app._memory_cache.clear()

    def _daily_frame(self, close: float, volume: float, days: int = 210) -> pd.DataFrame:
        idx = pd.date_range("2025-01-01", periods=days)
        return pd.DataFrame({"Close": close, "Volume": volume}, index=idx)

    def _weak_daily_frame(self, last_close: float, volume: float, days: int = 210) -> pd.DataFrame:
        idx = pd.date_range("2025-01-01", periods=days)
        closes = [100.0] * (days - 1) + [last_close]
        return pd.DataFrame({"Close": closes, "Volume": volume}, index=idx)

    def test_compute_signals_includes_short_pick_from_adv_top30_weakest_ma200(self) -> None:
        symbols = [f"S{i:02d}" for i in range(35)]
        history = {
            symbol: self._daily_frame(close=100.0 + idx, volume=1_000_000.0 - idx * 1_000.0)
            for idx, symbol in enumerate(symbols)
        }
        history["S29"] = self._weak_daily_frame(last_close=70.0, volume=2_000_000.0)
        history["S30"] = self._weak_daily_frame(last_close=10.0, volume=100.0)

        with (
            patch.object(app, "fetch_current_symbols", return_value=symbols),
            patch.object(app, "fetch_history", return_value=history),
        ):
            result = app.compute_signals("nasdaq100")

        self.assertEqual(result["short_proxy"], "QQQ")
        self.assertEqual(result["short_allocation"], {"proxy_pct": 70, "weak_stock_pct": 30})
        self.assertEqual(len(result["short_selected"]), 1)
        self.assertEqual(result["short_selected"][0]["symbol"], "S29")
        self.assertEqual(result["short_selected"][0]["rank"], 1)


class MarketStatusTests(unittest.TestCase):
    def test_breadth_status_uses_app_ntss_direction(self) -> None:
        status = app.classify_market_status({"s": 18.0, "bd": 58.0, "mid": -1.2, "mom": -0.5})

        self.assertEqual(status["signal"], "short")
        self.assertEqual(status["short_type"], "Risk Off")
        self.assertEqual(status["ntss_state"], "PANIC")
        self.assertIn("VIX3M - VIX", status["basis"])

    def test_breadth_status_marks_long_when_breakdown_below_35(self) -> None:
        status = app.classify_market_status({"s": 42.0, "bd": 28.0, "mid": 2.5, "mom": 0.4})

        self.assertEqual(status["signal"], "long")
        self.assertEqual(status["short_type"], None)
        self.assertEqual(status["phase_code"], "B")


class BreadthReferenceTests(unittest.TestCase):
    def test_format_breadth_bar_time_shows_half_hour_bar_end(self) -> None:
        ts = pd.Timestamp("2026-06-01 15:30", tz="America/New_York")

        self.assertEqual(app.format_breadth_bar_time(ts), "2026-06-01 16:00")

    def test_format_breadth_bar_time_leaves_full_hour_unchanged(self) -> None:
        ts = pd.Timestamp("2026-06-01 14:00", tz="America/New_York")

        self.assertEqual(app.format_breadth_bar_time(ts), "2026-06-01 14:00")

    def test_previous_day_close_record_uses_last_record_from_prior_day(self) -> None:
        records = [
            {"t": "2026-05-29 15:00", "s": 30.0},
            {"t": "2026-05-29 16:00", "s": 31.0},
            {"t": "2026-06-01 09:00", "s": 40.0},
            {"t": "2026-06-01 10:00", "s": 41.0},
        ]

        ref = app.previous_day_close_record(records)

        self.assertEqual(ref, {"t": "2026-05-29 16:00", "s": 31.0})

    def test_previous_day_close_record_returns_none_without_prior_day(self) -> None:
        records = [
            {"t": "2026-06-01 09:00", "s": 40.0},
            {"t": "2026-06-01 10:00", "s": 41.0},
        ]

        self.assertIsNone(app.previous_day_close_record(records))

    def test_daily_close_payload_waits_for_same_day_ntss(self) -> None:
        idx = pd.date_range("2025-06-02", periods=220, freq="B")
        daily = pd.DataFrame({
            "AAA": range(100, 100 + len(idx)),
            "BBB": range(200, 200 + len(idx)),
        }, index=idx)
        ntss = pd.Series(
            [2.0] * (len(idx) - 1),
            index=idx[:-1],
            name="ntss",
        )

        payload = app.daily_close_payload(daily, ntss, min_n=1)

        self.assertIsNotNone(payload)
        self.assertEqual(payload["current"]["t"], f"{idx[-2]:%Y-%m-%d} EOD")
        self.assertEqual(payload["previous"]["t"], f"{idx[-3]:%Y-%m-%d} EOD")

    def test_daily_breadth_uses_available_history_ma_for_short_histories(self) -> None:
        idx = pd.date_range("2026-01-01", periods=5, freq="B")
        daily = pd.DataFrame({
            "LONG": [10.0, 11.0, 12.0, 13.0, 14.0],
            "SHORT": [20.0, 20.0, 20.0, 20.0, 30.0],
            "BELOW": [50.0, 50.0, 50.0, 50.0, 40.0],
        }, index=idx)

        breadth = app._calculate_breadth_from_daily(daily, min_n=1, denominator=3)
        last = breadth.iloc[-1]

        self.assertEqual(last["above_200_n"], 2)
        self.assertEqual(last["valid_200_n"], 3)
        self.assertEqual(last["above_200"], 66.67)

    def test_daily_close_payload_reports_fixed_universe_denominator(self) -> None:
        idx = pd.date_range("2026-01-01", periods=5, freq="B")
        daily = pd.DataFrame({
            "AAA": [10.0, 10.0, 10.0, 10.0, 12.0],
            "BBB": [20.0, 20.0, 20.0, 20.0, 18.0],
        }, index=idx)

        payload = app.daily_close_payload(daily, min_n=1, denominator=3)

        self.assertIsNotNone(payload)
        self.assertEqual(payload["current"]["a200_n"], 1)
        self.assertEqual(payload["current"]["valid_200_n"], 2)
        self.assertEqual(payload["current"]["a200"], 33.33)


if __name__ == "__main__":
    unittest.main()
