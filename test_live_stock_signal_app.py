from __future__ import annotations

import importlib
import json
import re
import subprocess
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
    assert 'status.signal==="short"' in html
    assert 'status.signal==="short_watch"' in html
    assert "status.short_type" in html
    assert 'phase==="G"||phase==="H"' not in html
    assert 'ntss!==null&&ntss<0' not in html
    assert 'breakdown!==null&&breakdown>=35' not in html
    assert 'setText("shortRadarTitle","正在加载市场风险")' in html
    assert 'setText("qualityDisclosure","正在检查覆盖率与新鲜度。")' in html
    assert '<main id="dashboard"' in html
    assert 'aria-live="polite"' in html
    assert 'role="status"' in html
    assert 'setAttribute("role","alert")' in html
    assert 'setDashboardBusy(true)' in html
    assert 'setDashboardBusy(false)' in html


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


def test_dashboard_javascript_executes_state_transitions_and_safe_sorting(tmp_path, monkeypatch):
    _write_pair(tmp_path)
    html = TestClient(_import_app(monkeypatch, tmp_path).app).get("/").text
    scripts = re.findall(r"<script>(.*?)</script>", html, flags=re.S)
    dashboard_script = scripts[-1]
    harness = r'''
const ids = ["dashboard","runBtn","currentAction","actionBasis","marketPhase","phaseBadge",
 "freshnessBadge","dataTimestamp","strongValue","breakdownValue","ntssValue","momentumValue",
 "ntssState","shortRadarTitle","shortRadarText","qualityDisclosure","targetCount","buyTargetBody",
 "buyTargetTable","buyTargetMessage"];
function element(id) { return {id, textContent:"", className:"", hidden:false, children:[], attrs:{},
  style:{}, addEventListener(){}, setAttribute(k,v){this.attrs[k]=v;}, removeAttribute(k){delete this.attrs[k];},
  appendChild(v){this.children.push(v);}, replaceChildren(...v){this.children=v;} }; }
const elements = Object.fromEntries(ids.map(id => [id, element(id)]));
globalThis.document = {getElementById(id){return elements[id]||(elements[id]=element(id));}, createElement(tag){return element(tag);}};
globalThis.fetch = () => new Promise(() => {});
'''
    assertions = r'''
renderStatus({market_status:{phase_code:"B",phase:"强势整固",signal:"long",label:"多头窗口",
 action:"多头优先",strong:50,breakdown:20,ntss:-1,momentum:2,ntss_state:"PANIC"}});
setDashboardBusy(false);
if(elements.currentAction.textContent!=="多头窗口") throw new Error("success label");
if(elements.ntssState.textContent!=="PANIC") throw new Error("success ntss state");
if(elements.dashboard.attrs["aria-busy"]!=="false") throw new Error("success busy");
if(elements.shortRadarTitle.textContent.includes("Risk Off")) throw new Error("radar re-derived risk");
setLoading();
if(elements.ntssState.textContent!=="等待") throw new Error("loading ntss reset");
if(elements.dashboard.attrs["aria-busy"]!=="true") throw new Error("loading busy");
setUnavailable("boom");
if(elements.ntssState.textContent!=="—") throw new Error("error ntss reset");
if(elements.dashboard.attrs["aria-busy"]!=="false") throw new Error("error busy");
if(elements.buyTargetMessage.attrs.role!=="alert") throw new Error("missing alert");
const sorted=sortedTargets([{rank:2,universe:"sp500",symbol:"B"},{rank:1,universe:"sp500",symbol:"Z"},{rank:1,universe:"nasdaq100",symbol:"A"}]);
if(sorted.map(x=>x.symbol).join("")!=="AZB") throw new Error("sort contract");
const safe=cell("<img onerror=bad>"); if(safe.textContent!=="<img onerror=bad>") throw new Error("unsafe text");
'''
    result = subprocess.run(
        ["node", "-e", harness + dashboard_script + assertions],
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_breadth_page_is_lightweight_intraday_radar(tmp_path, monkeypatch):
    _write_pair(tmp_path)
    html = TestClient(_import_app(monkeypatch, tmp_path).app).get("/breadth").text

    for element_id in (
        "breadthDashboard", "breadthPhase", "breadthAction", "breadthFreshness",
        "breadthTimestamp", "strongValue", "strongDelta", "breakdownValue",
        "breakdownDelta", "ntssValue", "ntssDelta", "intradayChart",
        "latestTransition", "ma20Value", "ma50Value", "ma200Value",
        "momentumValue", "qualityDetails",
    ):
        assert f'id="{element_id}"' in html
    assert "<details" in html and "研究详情" in html
    assert "<svg" in html and "viewBox=" in html
    assert "Plotly" not in html and "plotly" not in html
    assert "innerHTML" not in html
    assert "document.createElementNS" in html
    assert 'aria-live="polite"' in html
    assert 'aria-busy="true"' in html
    assert "session_status" in html
    assert "latest_transition" in html


def test_breadth_javascript_renders_deltas_today_transition_and_resets_safely(tmp_path, monkeypatch):
    _write_pair(tmp_path)
    html = TestClient(_import_app(monkeypatch, tmp_path).app).get("/breadth").text
    script = re.findall(r"<script>(.*?)</script>", html, flags=re.S)[-1]
    harness = r'''
const ids=["breadthDashboard","refreshBtn","breadthPhase","phaseBadge","breadthAction",
 "breadthFreshness","breadthTimestamp","strongValue","strongDelta","breakdownValue",
 "breakdownDelta","ntssValue","ntssDelta","intradayChart","chartEmpty","latestTransition",
 "ma20Value","ma50Value","ma200Value","momentumValue","qualityDetails","latestBar"];
function el(id){return {id,textContent:"",className:"",hidden:false,children:[],attrs:{},style:{},
 addEventListener(){},setAttribute(k,v){this.attrs[k]=v;},appendChild(v){this.children.push(v);},
 replaceChildren(...v){this.children=v;}};}
const elements=Object.fromEntries(ids.map(id=>[id,el(id)]));
globalThis.document={getElementById(id){return elements[id]||(elements[id]=el(id));},
 createElementNS(ns,tag){const node=el(tag);node.tag=tag;return node;}};
globalThis.fetch=()=>new Promise(()=>{});
'''
    assertions = r'''
const data={generated_at:"2026-07-11T15:20:00Z",stale:false,
 quality:{session_status:"open",valid_count:498,failed_count:2},
 records:[
  {t:"2026-07-10T15:00:00Z",phase_code:"A",s:90,bd:1,mid:8},
  {t:"2026-07-11T14:45:00Z",phase_code:"B",phase_label:"强势整固",action:"继续持有",s:40,bd:20,mid:1,a20:55,a50:50,a200:45,mom:2,a20_n:490,a50_n:489,a200_n:480},
  {t:"2026-07-11T15:00:00Z",phase_code:"E",phase_label:"震荡整理",action:"降低仓位",s:43,bd:18,mid:.5,a20:56,a50:51,a200:46,mom:-1,a20_n:491,a50_n:490,a200_n:481}],
 latest_transition:{from:"B",from_label:"强势整固",to:"E",to_label:"震荡整理",at:"2026-07-11T15:00:00Z"}};
renderBreadth(data);
if(elements.breadthPhase.textContent!=="E 震荡整理") throw new Error("phase label");
if(elements.breadthAction.textContent!=="降低仓位") throw new Error("producer action");
if(elements.strongDelta.textContent!=="+3.0% vs 15 分钟前") throw new Error("strong delta "+elements.strongDelta.textContent);
if(elements.breakdownDelta.textContent!=="−2.0% vs 15 分钟前") throw new Error("breakdown delta");
if(elements.ntssDelta.textContent!=="−0.50 vs 15 分钟前") throw new Error("ntss delta");
if(elements.latestTransition.textContent.indexOf("B 强势整固 → E 震荡整理")<0) throw new Error("transition");
if(elements.intradayChart.children.length<4) throw new Error("chart not rendered");
if(!elements.intradayChart.children.some(x=>x.tag==="text"&&x.textContent==="E 震荡整理")) throw new Error("transition annotation");
if(elements.intradayChart.children.some(x=>String(x.attrs&&x.attrs.points||"").includes("90"))) throw new Error("prior day leaked");
if(elements.qualityDetails.textContent.indexOf("有效 498")<0) throw new Error("quality");
if(elements.breadthDashboard.attrs["aria-busy"]!=="false") throw new Error("busy success");
setLoading();
if(elements.strongValue.textContent!=="—"||elements.intradayChart.children.length!==0) throw new Error("loading reset");
if(elements.breadthDashboard.attrs["aria-busy"]!=="true") throw new Error("busy loading");
setUnavailable("<img onerror=bad>");
if(elements.breadthAction.textContent.indexOf("<img onerror=bad>")<0) throw new Error("safe error text");
if(elements.breadthFreshness.attrs.role!=="alert") throw new Error("alert state");
'''
    result = subprocess.run(["node", "-e", harness + script + assertions], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
