"""Report whether a snapshot refresh should run for the current NYSE session."""

from __future__ import annotations

import os
from datetime import datetime, timezone


def is_nyse_open(at: datetime, *, calendar=None) -> bool:
    """Return true only while the XNYS exchange calendar is open."""
    import pandas as pd

    if at.tzinfo is None:
        raise ValueError("at must be timezone-aware")
    if calendar is None:
        import exchange_calendars as xcals

        calendar = xcals.get_calendar("XNYS")
    return bool(calendar.is_open_on_minute(pd.Timestamp(at)))


def main() -> None:
    manual = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    should_run = manual or is_nyse_open(datetime.now(timezone.utc))
    output_path = os.environ.get("GITHUB_OUTPUT")
    line = f"should_run={str(should_run).lower()}\n"
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output:
            output.write(line)
    else:
        print(line, end="")


if __name__ == "__main__":
    main()
