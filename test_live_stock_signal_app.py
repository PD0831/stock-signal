from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pandas as pd

import live_stock_signal_app as app


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


if __name__ == "__main__":
    unittest.main()
