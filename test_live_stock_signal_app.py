from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from scripts.build_dashboard_snapshots import build_dashboard_snapshot, build_breadth_snapshot, run


def _write_pair(tmp_path, *, generated_at=None, schema_version=1, mismatch=False):
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    fresh_until = (datetime.fromisoformat(generated_at) + timedelta(hours=1)).isoformat()
    dashboard = {
        "schema_version": schema_version,
        "generation_id": "generation-a",
        "generated_at": generated_at,
        "market_status": {"phase_code": "B"},
        "quality": {"valid_count": 500, "fresh_until": fresh_until, "session_status": "open"},
        "buy_targets": [],
    }
    breadth = {
        "schema_version": schema_version,
        "generation_id": "generation-b" if mismatch else "generation-a",
        "generated_at": generated_at,
        "quality": {"valid_count": 500, "fresh_until": fresh_until, "session_status": "open"},
        "records": [],
        "latest_transition": None,
    }
    (tmp_path / "dashboard_snapshot.json").write_text(json.dumps(dashboard))
    (tmp_path / "breadth_15m.json").write_text(json.dumps(breadth))
    return dashboard, breadth


def _import_app(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    sys.modules.pop("live_stock_signal_app", None)
    return importlib.import_module("live_stock_signal_app")


def test_display_routes_use_snapshots_without_market_dependencies(tmp_path, monkeypatch):
    dashboard, breadth = _write_pair(tmp_path)
    # A display-only import must work even when market libraries are unavailable.
    monkeypatch.setitem(sys.modules, "yfinance", None)
    monkeypatch.setitem(sys.modules, "pandas", None)
    monkeypatch.setitem(sys.modules, "numpy", None)
    app_module = _import_app(monkeypatch, tmp_path)

    assert {route.path for route in app_module.app.router.routes} == {
        "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc",
        "/", "/breadth", "/api/signals", "/api/breadth",
    }
    assert type(app_module.app.router.lifespan_context).__name__ == "_DefaultLifespan"

    with TestClient(app_module.app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/breadth").status_code == 200
        signal_response = client.get("/api/signals")
        breadth_response = client.get("/api/breadth")

    assert signal_response.status_code == 200
    assert signal_response.json() | {"stale": False} == dashboard | {"stale": False}
    assert breadth_response.status_code == 200
    assert breadth_response.json() | {"stale": False} == breadth | {"stale": False}


def test_stale_snapshot_remains_available(tmp_path, monkeypatch):
    generated_at = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    _write_pair(tmp_path, generated_at=generated_at)
    app_module = _import_app(monkeypatch, tmp_path)

    response = TestClient(app_module.app).get("/api/signals")

    assert response.status_code == 200
    assert response.json()["stale"] is True
    assert response.json()["generated_at"] == generated_at


def test_future_generated_at_is_unavailable(tmp_path, monkeypatch):
    generated_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    _write_pair(tmp_path, generated_at=generated_at)
    app_module = _import_app(monkeypatch, tmp_path)

    response = TestClient(app_module.app).get("/api/signals")

    assert response.status_code == 503
    assert "future" in response.json()["error"].lower()


def test_incompatible_schema_is_unavailable_but_html_renders(tmp_path, monkeypatch):
    _write_pair(tmp_path, schema_version=99)
    app_module = _import_app(monkeypatch, tmp_path)
    client = TestClient(app_module.app)

    response = client.get("/api/signals")

    assert response.status_code == 503
    assert response.json()["available"] is False
    assert "schema" in response.json()["error"].lower()
    assert client.get("/").status_code == 200
    assert client.get("/breadth").status_code == 200


def test_schema_version_requires_exact_integer_type(tmp_path, monkeypatch):
    for schema_version in (True, 1.0):
        case_dir = tmp_path / repr(schema_version)
        case_dir.mkdir()
        _write_pair(case_dir, schema_version=schema_version)
        app_module = _import_app(monkeypatch, case_dir)

        response = TestClient(app_module.app).get("/api/signals")

        assert response.status_code == 503
        assert "schema" in response.json()["error"].lower()


def test_generation_mismatch_makes_both_apis_unavailable(tmp_path, monkeypatch):
    _write_pair(tmp_path, mismatch=True)
    app_module = _import_app(monkeypatch, tmp_path)
    client = TestClient(app_module.app)

    for route in ("/api/signals", "/api/breadth"):
        response = client.get(route)
        assert response.status_code == 503
        assert response.json()["available"] is False
        assert "generation" in response.json()["error"].lower()


def test_invalid_nested_dashboard_fields_are_unavailable(tmp_path, monkeypatch):
    _write_pair(tmp_path)
    path = tmp_path / "dashboard_snapshot.json"
    payload = json.loads(path.read_text())
    payload["buy_targets"] = [{"symbol": 123, "universe": "sp500", "rank": 1, "target_weight_pct": 60}]
    path.write_text(json.dumps(payload))
    app_module = _import_app(monkeypatch, tmp_path)

    response = TestClient(app_module.app).get("/api/signals")

    assert response.status_code == 503
    assert "symbol" in response.json()["error"]


def test_invalid_breadth_record_is_unavailable(tmp_path, monkeypatch):
    _write_pair(tmp_path)
    path = tmp_path / "breadth_15m.json"
    payload = json.loads(path.read_text())
    payload["records"] = [{"t": 123, "s": "high"}]
    path.write_text(json.dumps(payload))
    app_module = _import_app(monkeypatch, tmp_path)

    response = TestClient(app_module.app).get("/api/breadth")

    assert response.status_code == 503
    assert "record" in response.json()["error"]


def test_non_finite_json_is_unavailable(tmp_path, monkeypatch):
    _write_pair(tmp_path)
    path = tmp_path / "breadth_15m.json"
    path.write_text(path.read_text().replace('"records": []', '"records": [{"t":"now","s":NaN}]'))
    app_module = _import_app(monkeypatch, tmp_path)

    response = TestClient(app_module.app).get("/api/breadth")

    assert response.status_code == 503
    assert "finite" in response.json()["error"].lower()


def test_malicious_target_is_rejected(tmp_path, monkeypatch):
    _write_pair(tmp_path)
    path = tmp_path / "dashboard_snapshot.json"
    payload = json.loads(path.read_text())
    payload["buy_targets"] = [{
        "symbol": "<img src=x onerror=alert(1)>", "universe": "sp500",
        "rank": 1, "target_weight_pct": 60,
    }]
    path.write_text(json.dumps(payload))
    app_module = _import_app(monkeypatch, tmp_path)

    assert TestClient(app_module.app).get("/api/signals").status_code == 503


def test_web_module_has_no_live_market_or_network_code():
    source = (Path(__file__).parent / "live_stock_signal_app.py").read_text()
    for forbidden in ("yfinance", "requests", "pandas", "numpy", "threading", "socket", "compute_signals", "compute_breadth"):
        assert forbidden not in source


def test_actual_builder_payload_is_served_and_homepage_consumes_buy_targets(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    quality = {
        "fresh_until": (now + timedelta(hours=1)).isoformat(),
        "session_status": "open",
    }
    dashboard = build_dashboard_snapshot(
        {"sp500": [{"symbol": "AAPL", "rank": 1}]},
        generated_at=now, market_status={}, quality=quality,
    )
    breadth = build_breadth_snapshot([], generated_at=now, quality=quality)
    dashboard["generation_id"] = breadth["generation_id"] = "integration"
    (tmp_path / "dashboard_snapshot.json").write_text(json.dumps(dashboard))
    (tmp_path / "breadth_15m.json").write_text(json.dumps(breadth))
    app_module = _import_app(monkeypatch, tmp_path)
    client = TestClient(app_module.app)

    assert client.get("/api/signals").status_code == 200
    html = client.get("/").text
    assert "data.buy_targets" in html
    assert "data.nasdaq100" not in html
    assert "data.sp500" not in html
    assert "innerHTML" not in html
    assert "textContent" in html


def test_homepage_is_action_first_professional_decision_dashboard(tmp_path, monkeypatch):
    _write_pair(tmp_path)
    app_module = _import_app(monkeypatch, tmp_path)

    html = TestClient(app_module.app).get("/").text

    # Stable action/freshness and four-indicator contracts.
    for element_id in (
        "currentAction", "marketPhase", "freshnessBadge", "dataTimestamp",
        "strongValue", "breakdownValue", "ntssValue", "momentumValue",
        "buyTargetBody", "buyTargetMessage", "shortRadar", "qualityDisclosure",
    ):
        assert f'id="{element_id}"' in html

    # One combined, semantic professional table in the approved C layout.
    assert '<table id="buyTargetTable"' in html
    headings = (
        "排名", "标的", "市场", "MA200 距离", "目标权重", "最新价", "ADV 排名", "数据时间",
    )
    assert [html.index(f">{heading}</th>") for heading in headings] == sorted(
        html.index(f">{heading}</th>") for heading in headings
    )
    assert "NASDAQ 100 / QQQ" not in html
    assert "S&amp;P 500 / SPY" not in html

    # Snapshot data is rendered through safe DOM APIs, never string HTML.
    assert "data.buy_targets" in html
    assert "document.createElement" in html
    assert ".textContent" in html
    assert "innerHTML" not in html
    assert "localeCompare" in html
    assert "overflow-x: auto" in html
    assert "@media (max-width:640px)" in html
    assert "nth-child(3)" in html and "nth-child(5)" in html
    assert "display:none" in html
    assert "setText(\"targetCount\",\"0 个\")" in html
    assert "setText(\"dataTimestamp\",\"数据时间 —\")" in html
    assert "universe_source" in html
    assert "universe_warning" in html
    assert "候选不足" in html
    assert "const PHASES" not in html
    assert "status.phase" in html and "status.label" in html and "status.action" in html
    assert 'phase==="G"||phase==="H"' in html
    assert 'ntss!==null&&ntss<0' in html
    assert 'breakdown!==null&&breakdown>=35' in html
    assert 'setText("shortRadarTitle","正在加载市场风险")' in html
    assert 'setText("qualityDisclosure","正在检查覆盖率与新鲜度。")' in html


def test_builder_market_status_contract_is_consumed_by_homepage(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    class Provider:
        def compute_signals(self, universe):
            return {"valid_count": 100, "failed_count": 2, "ma200_selected": [
                {"symbol": "AAPL", "rank": 1, "distance_pct": 12.5}
            ]}

        def compute_breadth(self):
            return {"n_stocks": 500, "n_valid_15m": 498, "records": [{
                "t": now.isoformat(), "phase_code": "C", "s": 57.5,
                "bd": 13.5, "mid": 1.25, "mom": 4.5,
            }]}

    run(tmp_path, provider=Provider(), generated_at=now)
    client = TestClient(_import_app(monkeypatch, tmp_path).app)
    response = client.get("/api/signals")
    assert response.status_code == 200
    assert response.json()["market_status"] | {"as_of": now.isoformat()} == {
        "phase_code": "C", "phase": "牛市回调", "signal": "long",
        "phase_class": "safe", "label": "多头窗口", "short_type": None,
        "ntss_state": "CAUTION", "ntss_class": "caution",
        "action": "多头优先：使用 ADV Top10 → MA200 Top3。",
        "basis": "NTSS = VIX3M - VIX; positive=calm, negative=panic",
        "as_of": now.isoformat(), "strong": 57.5, "breakdown": 13.5,
        "ntss": 1.25, "momentum": 4.5,
    }
    html = client.get("/").text

    for contract_value in ("strong", "breakdown", "ntss", "momentum", "action", "distance_pct"):
        assert f'status.{contract_value}' in html or f'target.{contract_value}' in html
