from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess

from scripts import nyse_market_hours as hours


def test_delayed_close_run_catches_missing_final_bar(tmp_path):
    path = tmp_path / 'breadth_15m.json'
    path.write_text(json.dumps({'records': [{'t':'2026-09-18T19:15:00Z'}]}))
    assert hours.should_refresh(datetime.fromisoformat('2026-09-18T21:46:00+00:00'), snapshot_path=path)
    path.write_text(json.dumps({'generated_at':'2026-09-18T20:07:00Z','records': [{'t':'2026-09-18T19:45:00Z'}]}))
    assert not hours.should_refresh(datetime.fromisoformat('2026-09-18T21:46:00+00:00'), snapshot_path=path)


def test_refresh_gate_respects_holidays_early_close_and_open_session(tmp_path):
    path = tmp_path / 'missing.json'
    for date, expected in [('2026-09-21T15:00:00+00:00',True),('2026-09-19T15:00:00+00:00',False),('2026-07-03T15:00:00+00:00',False),('2026-11-27T19:00:00+00:00',True),('2026-09-21T12:00:00+00:00',False)]:
        assert hours.should_refresh(datetime.fromisoformat(date), snapshot_path=path) is expected


def test_polling_refreshes_visible_page_and_retries_after_failure():
    from dashboard_html import _AUTO_REFRESH
    script = r'''
const listeners={};let callback,calls=0;
globalThis.document={hidden:false,addEventListener:(k,v)=>listeners[k]=v};
globalThis.window={setInterval:(fn,ms)=>{callback=fn;if(ms!==60000)throw Error('interval')}};
''' + _AUTO_REFRESH + r'''
(async()=>{
startSnapshotPolling(async()=>{calls++;if(calls===1)throw Error('network')});
await callback();await callback();if(calls!==2)throw Error('retry');
document.hidden=true;await callback();if(calls!==2)throw Error('hidden');
document.hidden=false;await listeners.visibilitychange();if(calls!==3)throw Error('visible');
let release;startSnapshotPolling(()=>new Promise(r=>{calls++;release=r}));
const a=callback();await callback();if(calls!==4)throw Error('overlap');release();await a;
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result=subprocess.run(['node','-e',script],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


def test_forming_last_bar_does_not_suppress_close_refresh(tmp_path):
    path=tmp_path / 'breadth_15m.json'
    path.write_text(json.dumps({'generated_at':'2026-09-18T19:52:00Z','records':[{'t':'2026-09-18T19:45:00Z'}]}))
    assert hours.should_refresh(datetime.fromisoformat('2026-09-18T20:07:00+00:00'),snapshot_path=path)


def _gate_output(monkeypatch, tmp_path, force):
    out = tmp_path / f'out-{force}.txt'
    monkeypatch.setenv('GITHUB_OUTPUT', str(out))
    if force is None:
        monkeypatch.delenv('FORCE_REFRESH', raising=False)
    else:
        monkeypatch.setenv('FORCE_REFRESH', force)
    monkeypatch.setattr(hours, 'should_refresh', lambda at: False)
    hours.main()
    return out.read_text()


def test_dispatch_without_force_stays_calendar_gated(monkeypatch, tmp_path):
    assert _gate_output(monkeypatch, tmp_path, None) == 'should_run=false\n'
    assert _gate_output(monkeypatch, tmp_path, '') == 'should_run=false\n'
    assert _gate_output(monkeypatch, tmp_path, 'false') == 'should_run=false\n'


def test_forced_dispatch_bypasses_calendar_gate(monkeypatch, tmp_path):
    assert _gate_output(monkeypatch, tmp_path, 'true') == 'should_run=true\n'


def _expand_cron_field(field: str) -> list[int]:
    values: list[int] = []
    for part in field.split(","):
        if "-" in part:
            start, end = (int(piece) for piece in part.split("-"))
            values.extend(range(start, end + 1))
        else:
            values.append(int(part))
    return values


def _cron_slots(cron: str, day) -> list[datetime]:
    minute_field, hour_field, dom, month, dow = cron.split()
    assert dom == "*" and month == "*", cron
    dows = set(_expand_cron_field(dow))
    cron_dow = (day.weekday() + 1) % 7
    if cron_dow not in dows and not (cron_dow == 0 and 7 in dows):
        return []
    return [
        datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc)
        for hour in _expand_cron_field(hour_field)
        for minute in _expand_cron_field(minute_field)
    ]


def _refresh_crons() -> list[str]:
    import yaml

    workflow_path = Path(__file__).parents[1] / ".github" / "workflows" / "refresh_dashboard.yml"
    parsed = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    parsed["on"] = parsed.pop(True, parsed.get("on"))
    return [item["cron"] for item in parsed["on"]["schedule"]]


def _slots_on(day) -> list[datetime]:
    slots: list[datetime] = []
    for cron in _refresh_crons():
        slots.extend(_cron_slots(cron, day))
    return slots


def test_month_end_close_has_post_close_refresh_slot(tmp_path):
    """The weekday cron already runs after the last XNYS close; do not add slots.

    EDT regular close is 20:00 UTC (first post-close slot 20:07). EST regular close
    is 21:00 UTC, so hour 21 is required (first post-close slot 21:07). An early-close
    month-end is earlier. A start delayed past UTC midnight still passes the gate while
    it is inside the six-hour window, because that window is still the session's ET date.
    """
    import exchange_calendars as xcals
    import pandas as pd

    calendar = xcals.get_calendar("XNYS")

    def first_slot_after_close(session_day: str):
        close = pd.Timestamp(calendar.session_close(pd.Timestamp(session_day))).to_pydatetime()
        close = close.astimezone(timezone.utc)
        slots = [
            slot for slot in _slots_on(close.date())
            if close < slot <= close + timedelta(hours=6)
        ]
        assert slots, (session_day, close.isoformat())
        return min(slots), close

    # October 2026 month-end is a Friday in EDT. The observed build was 22:37 UTC.
    slot, close = first_slot_after_close("2026-10-30")
    assert slot == datetime(2026, 10, 30, 20, 7, tzinfo=timezone.utc)
    snapshot = tmp_path / "breadth_15m.json"
    snapshot.write_text(json.dumps({
        "generated_at": "2026-10-30T19:40:00+00:00",
        "records": [{"t": "2026-10-30T19:45:00+00:00"}],
    }))
    assert hours.should_refresh(slot, snapshot_path=snapshot)
    assert hours.should_refresh(datetime.fromisoformat("2026-10-30T22:37:17+00:00"), snapshot_path=snapshot)
    assert hours.should_refresh(datetime.fromisoformat("2026-10-31T01:30:00+00:00"), snapshot_path=snapshot)
    assert not hours.should_refresh(datetime.fromisoformat("2026-10-31T15:00:00+00:00"), snapshot_path=snapshot)
    assert _slots_on(datetime(2026, 10, 31, tzinfo=timezone.utc).date()) == []

    # December 2025 month-end is a Wednesday in EST. Hour 20 is still before the close.
    slot, close = first_slot_after_close("2025-12-31")
    assert close == datetime(2025, 12, 31, 21, 0, tzinfo=timezone.utc)
    assert slot == datetime(2025, 12, 31, 21, 7, tzinfo=timezone.utc)
    snapshot.write_text(json.dumps({
        "generated_at": "2025-12-31T20:40:00+00:00",
        "records": [{"t": "2025-12-31T20:45:00+00:00"}],
    }))
    assert hours.should_refresh(slot, snapshot_path=snapshot)

    # November 2025 month-end is Black Friday, an early close at 13:00 ET / 18:00 UTC.
    slot, close = first_slot_after_close("2025-11-28")
    assert close == datetime(2025, 11, 28, 18, 0, tzinfo=timezone.utc)
    assert slot == datetime(2025, 11, 28, 18, 7, tzinfo=timezone.utc)
    snapshot.write_text(json.dumps({
        "generated_at": "2025-11-28T17:40:00+00:00",
        "records": [{"t": "2025-11-28T17:45:00+00:00"}],
    }))
    assert hours.should_refresh(slot, snapshot_path=snapshot)
