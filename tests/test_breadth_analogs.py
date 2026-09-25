import json
import math

import numpy as np
import pandas as pd

from scripts import breadth_analogs as analogs


def _history(days=900):
    index = pd.bdate_range("2015-01-01", periods=days)
    rng = np.random.default_rng(0)
    qqq = 100 * np.cumprod(1 + rng.normal(0.0004, 0.01, days))
    strong = 40 + 20 * np.sin(np.arange(days) / 40)
    breakdown = 60 - strong
    return pd.DataFrame(
        {"qqq": qqq, "strong": strong, "breakdown": breakdown,
         "pullback": np.full(days, 10.0), "recovery": np.full(days, 5.0), "mid": np.full(days, 2.5)},
        index=pd.DatetimeIndex(index, name="date"),
    )


def test_pine_components_match_strategy_definition():
    comps = analogs.pine_components(a20=31.01, a50=26.84, a200=46.32)
    assert comps["strong"] == 26.84
    assert round(comps["breakdown"], 2) == 53.68
    assert round(comps["pullback"], 2) == 19.48   # s5th - s5fi
    assert round(comps["recovery"], 2) == 4.17    # s5tw - s5fi


def test_net_momentum_counts_only_positive_increments():
    prev = {"strong": 30, "recovery": 5, "pullback": 10, "breakdown": 40}
    cur = {"strong": 20, "recovery": 5, "pullback": 12, "breakdown": 44}
    # Strong falling contributes nothing; pullback +2 and breakdown +4 count.
    assert analogs.pine_net_momentum(cur, prev) == -6


def test_analog_stats_is_json_safe_and_uses_fixed_buckets():
    history = _history()
    result = analogs.analog_stats(history, {"strong": 25, "breakdown": 35, "mid": 2.5, "qqq": None})
    json.dumps(result, allow_nan=False)
    labels = [row["label"] for row in result["rows"]]
    assert labels[0].startswith("基准") and labels[1].startswith("基准")
    assert result["rows"][0]["n_events"] is None and result["rows"][0]["thin"] is False
    assert result["rows"][-1]["condition"] == "NTSS ≥ 2（SAFE）"
    similar = result["rows"][2]
    assert similar["n_days"] > 0 and similar["n_events"] >= 1
    for row in result["rows"]:
        for key in ("f20_mean", "f60_mean", "mdd60_median"):
            assert row[key] is None or math.isfinite(row[key])
        assert row["mdd60_median"] is None or row["mdd60_median"] <= 0


def test_forward_windows_never_use_rows_beyond_history():
    frame = analogs._prepare(_history(300))
    assert frame["f60"].iloc[-60:].isna().all()
    assert frame["mdd60"].iloc[-60:].isna().all()


def test_risk_off_zone_follows_pine_levels():
    history = _history()
    zone = analogs.analog_stats(history, {"strong": 20, "breakdown": 55, "mid": 1.0, "net_momentum": -2.0})["risk_off"]
    assert zone["zone"] is True and zone["net_momentum"] == -2.0
    clear = analogs.analog_stats(history, {"strong": 40, "breakdown": 45, "mid": 1.0})["risk_off"]
    assert clear["zone"] is False and clear["breakdown_gt_50"] is False


def test_build_analogs_missing_inputs_return_none(tmp_path):
    assert analogs.build_analogs(tmp_path, None, None) is None
    _history().to_csv(tmp_path / analogs.HISTORY_FILE)
    assert analogs.build_analogs(tmp_path, {"current": {"a20": 1}}, None) is None
    daily = {"current": {"a20": 31.0, "a50": 27.0, "a200": 46.0, "mid": 3.0},
             "previous": {"a20": 26.0, "a50": 25.0, "a200": 45.0}}
    result = analogs.build_analogs(tmp_path, daily, {"qqq": 120.0})
    assert result is not None and math.isfinite(result["risk_off"]["net_momentum"])


def test_committed_history_file_is_clean():
    frame = analogs.load_history(__import__("pathlib").Path("data") / analogs.HISTORY_FILE)
    assert frame.index.is_monotonic_increasing and frame.index.is_unique
    assert frame["qqq"].gt(0).all()
    breadth = frame.dropna(subset=["strong", "breakdown"])
    assert breadth.index[0] <= pd.Timestamp("2007-01-31")
    assert breadth[["strong", "breakdown"]].stack().between(0, 100).all()
