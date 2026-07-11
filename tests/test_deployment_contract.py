from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]


def test_render_uses_snapshot_only_single_worker_runtime():
    render = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    service = render["services"][0]
    env = {item["key"]: item["value"] for item in service["envVars"]}

    assert env["DATA_DIR"] == "data"
    assert env["WEB_CONCURRENCY"] == "1"
    assert "--workers 1" in service["startCommand"]


def test_web_runtime_dependencies_exclude_market_build_stack():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()

    for heavy_dependency in ("pandas", "numpy", "yfinance", "lxml", "html5lib"):
        assert heavy_dependency not in requirements
    assert "fastapi" in requirements
    assert "uvicorn" in requirements


def test_memory_smoke_script_exists_and_checks_all_public_routes():
    script = (ROOT / "scripts" / "memory_smoke.py").read_text(encoding="utf-8")

    for route in ('"/"', '"/api/signals"', '"/breadth"', '"/api/breadth"'):
        assert route in script
    assert "256" in script
