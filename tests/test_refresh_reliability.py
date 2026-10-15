from datetime import datetime
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


def test_overlapping_triggers_skip_recent_in_session_snapshot(tmp_path, monkeypatch):
    path = tmp_path / 'breadth_15m.json'
    path.write_text(json.dumps({'generated_at': '2026-09-18T15:00:00Z', 'records': [{'t': '2026-09-18T14:45:00Z'}]}))
    monkeypatch.delenv('MIN_REFRESH_MINUTES', raising=False)
    assert not hours.should_refresh(datetime.fromisoformat('2026-09-18T15:07:00+00:00'), snapshot_path=path)
    assert hours.should_refresh(datetime.fromisoformat('2026-09-18T15:15:00+00:00'), snapshot_path=path)
    monkeypatch.setenv('MIN_REFRESH_MINUTES', '25')
    assert not hours.should_refresh(datetime.fromisoformat('2026-09-18T15:15:00+00:00'), snapshot_path=path)
    assert hours.should_refresh(datetime.fromisoformat('2026-09-18T15:30:00+00:00'), snapshot_path=path)
