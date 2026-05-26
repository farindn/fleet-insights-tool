"""Validate that GeotabClient.get_exception_events_feed returns correct counts after the fix."""
from __future__ import annotations

import asyncio
import sys
from datetime import date
from collections import Counter

sys.path.insert(0, ".")

from app.services.geotab import GeotabClient

DEFAULTS = {
    "username": "",  # set via env MYG_USERNAME or edit here
    "password": "",  # set via env MYG_PASSWORD or edit here
    "database": "",  # set via env MYG_DATABASE or edit here
    "server": "my.geotab.com",
}


def af_month(ev: dict) -> str:
    af = ev.get("activeFrom")
    if af is None:
        return ""
    from datetime import datetime as dt
    if isinstance(af, dt):
        return af.strftime("%Y-%m")
    return str(af)[:7]


async def main() -> None:
    from_date = date(2026, 4, 1)
    to_date = date(2026, 4, 30)
    rule_id = "RuleJackrabbitStartsId"

    print(f"[setup] db={DEFAULTS['database']} rule={rule_id} window={from_date}..{to_date}")

    client = GeotabClient(
        username=DEFAULTS["username"],
        password=DEFAULTS["password"],
        database=DEFAULTS["database"],
        server=DEFAULTS["server"],
    )
    await client.authenticate()
    print("[setup] authenticated")

    print("[test] calling GeotabClient.get_exception_events_feed...")
    events = await client.get_exception_events_feed(rule_id, from_date, to_date)

    count = len(events)
    unique = len({e.get("id") for e in events if e.get("id")})
    af_months = Counter(af_month(e) for e in events)

    print(f"    total rows={count}  unique_ids={unique}")
    print(f"    activeFrom by month: {dict(sorted(af_months.items()))}")

    out_of_window = 0
    for e in events:
        af = e.get("activeFrom")
        from datetime import datetime as dt
        if isinstance(af, dt):
            if af.date() < from_date or af.date() > to_date:
                out_of_window += 1
    print(f"    events with activeFrom OUTSIDE [{from_date}..{to_date}]: {out_of_window}")

    print()
    print("-" * 60)
    print(f"Result: {count} events")
    print("Expected (UI ground truth): ~73,596")
    if 73000 <= count <= 74000:
        print("PASS - within expected range")
    else:
        print("FAIL - count outside expected range")


if __name__ == "__main__":
    asyncio.run(main())
