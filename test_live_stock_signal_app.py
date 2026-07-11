from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient


def _write_pair(tmp_path, *, generated_at=None, schema_version=1, mismatch=False):
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    dashboard = {
        "schema_version": schema_version,
        "generation_id": "generation-a",
        "generated_at": generated_at,
        "market_status": {"phase_code": "B"},
        "quality": {"valid_count": 500},
        "buy_targets": [],
    }
    breadth = {
        "schema_version": schema_version,
        "generation_id": "generation-b" if mismatch else "generation-a",
        "generated_at": generated_at,
        "quality": {"valid_count": 500},
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


def test_web_module_has_no_live_market_or_network_code():
    source = (Path(__file__).parent / "live_stock_signal_app.py").read_text()
    for forbidden in ("yfinance", "requests", "pandas", "numpy", "threading", "socket", "compute_signals", "compute_breadth"):
        assert forbidden not in source
