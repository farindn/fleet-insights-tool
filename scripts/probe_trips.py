"""Probe trip counts to identify truncation issues."""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, ".")

import mygeotab

DEFAULTS = {
    "username": "",  # set via env MYG_USERNAME
    "password": "",  # set via env MYG_PASSWORD
    "database": "",  # set via env MYG_DATABASE
    "server": "my.geotab.com",
}


async def main() -> None:
    from_date = date(2026, 4, 1)
    to_date = date(2026, 4, 30)

    print(f"[setup] db={DEFAULTS['database']} window={from_date}..{to_date}")

    api = mygeotab.API(
        username=DEFAULTS["username"],
        password=DEFAULTS["password"],
        database=DEFAULTS["database"],
        server=DEFAULTS["server"],
    )
    api.authenticate()
    print("[setup] authenticated")

    # Method 1: single call (will hit 50k cap)
    print("\n[1] Single api.get('Trip') call with resultsLimit=50000")
    from_dt = datetime.combine(from_date, datetime.min.time()).isoformat()
    to_dt = datetime.combine(to_date, datetime.max.time()).isoformat()

    single_trips = api.get("Trip", search={"fromDate": from_dt, "toDate": to_dt}, resultsLimit=50_000)
    print(f"    rows: {len(single_trips)}")
    if len(single_trips) >= 50_000:
        print("    WARNING: hit 50k cap - results truncated")

    # Method 2: day-by-day (to get true count + totals in one pass)
    print("\n[2] Day-by-day api.get('Trip') calls")
    all_trips = []
    caps_hit = 0
    cur = from_date
    while cur <= to_date:
        d_from = datetime.combine(cur, datetime.min.time()).isoformat()
        d_to = datetime.combine(cur, datetime.max.time()).isoformat()
        day_trips = api.get("Trip", search={"fromDate": d_from, "toDate": d_to}, resultsLimit=50_000)
        all_trips.extend(day_trips)
        if len(day_trips) >= 50_000:
            print(f"    {cur}: {len(day_trips)} trips - WARNING hit cap")
            caps_hit += 1
        cur += timedelta(days=1)

    print(f"    total rows: {len(all_trips)}")
    print(f"    days that hit 50k cap: {caps_hit}")

    print("\n[3] Computing totals from day-by-day data")
    total_distance = sum((t.get("distance") or 0) / 1000 for t in all_trips)  # m -> km
    total_driving = sum((t.get("drivingDuration") or timedelta(0)).total_seconds() / 3600
                        if hasattr(t.get("drivingDuration"), 'total_seconds')
                        else 0 for t in all_trips)
    total_idling = sum((t.get("idlingDuration") or timedelta(0)).total_seconds() / 3600
                       if hasattr(t.get("idlingDuration"), 'total_seconds')
                       else 0 for t in all_trips)
    total_stops = sum(t.get("stopCount") or t.get("numberOfStops") or 0 for t in all_trips)

    print(f"    Total distance: {total_distance:,.2f} km")
    print(f"    Total driving: {total_driving:,.1f} hours")
    print(f"    Total idling: {total_idling:,.1f} hours")
    print(f"    Total stops: {total_stops:,}")

    # Sample trip to see available fields
    if all_trips:
        print(f"\n[4] Sample trip fields: {list(all_trips[0].keys())}")


if __name__ == "__main__":
    asyncio.run(main())
