import json
import subprocess
import sys
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
    assert "scripts/network_guard.py -- uvicorn" in service["startCommand"]


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
    assert "network_guard.py" in script


def test_network_guard_blocks_and_records_adversarial_egress_paths(tmp_path):
    log = tmp_path / "blocked-egress.jsonl"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "network_guard.py"), "--probe-all"],
        env={"EGRESS_LOG": str(log)},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    attempts = [json.loads(line) for line in log.read_text().splitlines()]
    operations = {attempt["operation"] for attempt in attempts}
    assert {"connect", "connect_ex", "create_connection", "sendto", "send", "sendall", "getaddrinfo"} <= operations
    if hasattr(__import__("socket").socket, "sendmsg"):
        assert "sendmsg" in operations
    assert {attempt["host"] for attempt in attempts} >= {"203.0.113.1", "example.com"}


def test_network_guarded_memory_smoke_serves_all_routes_without_egress():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "memory_smoke.py"), "--iterations", "3"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "startup_rss_mib=" in result.stdout
    assert "peak_rss_mib=" in result.stdout
    assert "peak_growth_mib=" in result.stdout
    assert "final_growth_mib=" in result.stdout
