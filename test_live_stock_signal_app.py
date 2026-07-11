from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone

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


def test_generation_mismatch_makes_both_apis_unavailable(tmp_path, monkeypatch):
    _write_pair(tmp_path, mismatch=True)
    app_module = _import_app(monkeypatch, tmp_path)
    client = TestClient(app_module.app)

    for route in ("/api/signals", "/api/breadth"):
        response = client.get(route)
        assert response.status_code == 503
        assert response.json()["available"] is False
        assert "generation" in response.json()["error"].lower()
