"""Report whether a snapshot refresh should run for the current NYSE session."""

from __future__ import annotations

import os
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime, timezone, timedelta


def is_nyse_open(at: datetime, *, calendar=None) -> bool:
    """Return true only while the XNYS exchange calendar is open."""
    import pandas as pd

    if at.tzinfo is None:
        raise ValueError("at must be timezone-aware")
    if calendar is None:
        import exchange_calendars as xcals

        calendar = xcals.get_calendar("XNYS")
    return bool(calendar.is_open_on_minute(pd.Timestamp(at)))


def should_refresh(at: datetime, *, snapshot_path: Path = Path("data/breadth_15m.json"), calendar=None) -> bool:
    """Refresh in-session, and catch up a delayed run after the same session closes."""
    import pandas as pd
    if at.tzinfo is None:
        raise ValueError("at must be timezone-aware")
    if calendar is None:
        import exchange_calendars as xcals
        calendar = xcals.get_calendar("XNYS")
    day = pd.Timestamp(at.astimezone(ZoneInfo("America/New_York")).date())
    if not calendar.is_session(day):
        return False
    opened, closed = calendar.session_open(day), calendar.session_close(day)
    now = pd.Timestamp(at)
    if now < opened or now > closed + timedelta(hours=6):
        return False
    if now < closed:
        return True
    try:
        snapshot = json.loads(snapshot_path.read_text())
        records = snapshot["records"]
        generated = pd.Timestamp(snapshot["generated_at"])
        latest = max(pd.Timestamp(row["t"]) for row in records)
        return generated < closed or latest < closed - timedelta(minutes=15)
    except (OSError, ValueError, KeyError, TypeError):
        return True


def main() -> None:
    # External schedulers dispatch without inputs and stay calendar-gated;
    # only an explicit force=true (manual recovery) bypasses the gate.
    forced = os.environ.get("FORCE_REFRESH", "").strip().lower() == "true"
    should_run = forced or should_refresh(datetime.now(timezone.utc))
    output_path = os.environ.get("GITHUB_OUTPUT")
    line = f"should_run={str(should_run).lower()}\n"
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output:
            output.write(line)
    else:
        print(line, end="")


if __name__ == "__main__":
    main()
