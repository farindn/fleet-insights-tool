"""
Empirical probe to identify the source of inflated ExceptionEvent counts.

Compares three approaches for the same (rule_id, from_date, to_date) window:
  1. api.get("ExceptionEvent", search={fromDate, toDate, ruleSearch})  — naive single call
  2. api.call("GetFeed", typeName="ExceptionEvent", ...)                — cursor pagination
  3. api.call("GetReportData", argument={...})                          — server-side aggregation

Usage (PowerShell):
  $env:MYG_USERNAME="you@geotab.com"
  $env:MYG_PASSWORD="your-password"
  $env:MYG_DATABASE="your_database"
  $env:MYG_RULE_NAME="Hard Acceleration"   # OR set $env:MYG_RULE_ID
  $env:MYG_FROM="2026-04-01"
  $env:MYG_TO="2026-04-30"
  python scripts\probe_exception_counts.py

The script prints:
  - rule name resolved from the id
  - count from each approach
  - sample of activeFrom timestamps from the Get and GetFeed results (to verify the
    server is respecting toDate vs leaking later events into the result set)
  - GetReportData raw response shape for the first row (so we can see what fields
    a server-side aggregation actually exposes)
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta
from collections import Counter

import mygeotab


def af_month(ev: dict) -> str:
    """Get the YYYY-MM bucket of activeFrom, handling both str and datetime."""
    af = ev.get("activeFrom")
    if af is None:
        return ""
    if isinstance(af, datetime):
        return af.strftime("%Y-%m")
    s = str(af)
    return s[:7]


def env(name: str, required: bool = True) -> str:
    v = os.environ.get(name, "").strip()
    if required and not v:
        print(f"ERROR: env var {name} is required", file=sys.stderr)
        sys.exit(2)
    return v


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


# ─── Probe configuration (edit these values, or override via env vars) ─────────
# WARNING: do not commit this file with a real password. Delete the credentials
# below once the probe is finished.
DEFAULTS = {
    "MYG_USERNAME": "",
    "MYG_PASSWORD": "",
    "MYG_DATABASE": "",
    "MYG_SERVER":   "my.geotab.com",
    "MYG_RULE_NAME": "",
    "MYG_RULE_ID": "",
    "MYG_FROM": "",
    "MYG_TO":   "",
}


def cfg(name: str, required: bool = True) -> str:
    v = (os.environ.get(name) or DEFAULTS.get(name) or "").strip()
    if required and not v:
        print(f"ERROR: {name} is not set (env var or DEFAULTS)", file=sys.stderr)
        sys.exit(2)
    return v


def main() -> None:
    username = cfg("MYG_USERNAME")
    password = cfg("MYG_PASSWORD")
    database = cfg("MYG_DATABASE")
    rule_id = cfg("MYG_RULE_ID", required=False)
    rule_name_in = cfg("MYG_RULE_NAME", required=False)
    if not rule_id and not rule_name_in:
        print("ERROR: set either MYG_RULE_ID or MYG_RULE_NAME", file=sys.stderr)
        sys.exit(2)
    from_date = parse_date(cfg("MYG_FROM"))
    to_date = parse_date(cfg("MYG_TO"))
    server = cfg("MYG_SERVER")

    from_dt = datetime.combine(from_date, datetime.min.time()).isoformat()
    to_dt = datetime.combine(to_date, datetime.max.time()).isoformat()

    print(f"[setup] db={database} window={from_date}..{to_date}")
    api = mygeotab.API(username=username, password=password, database=database, server=server)
    api.authenticate()
    print("[setup] authenticated")

    if not rule_id:
        all_rules = api.get("Rule")
        match = [r for r in all_rules if r.get("name", "").strip().lower() == rule_name_in.strip().lower()]
        if not match:
            partial = [r for r in all_rules if rule_name_in.strip().lower() in r.get("name", "").lower()]
            print(f"[setup] no exact rule match for {rule_name_in!r}. Partial matches:")
            for r in partial[:10]:
                print(f"        id={r.get('id')}  name={r.get('name')!r}")
            sys.exit(3)
        rule_id = match[0]["id"]
        rule_name = match[0]["name"]
    else:
        rule = api.get("Rule", search={"id": rule_id})
        rule_name = rule[0].get("name", "?") if rule else "?"
    print(f"[setup] rule: id={rule_id} name={rule_name!r}")
    print()

    # ── Approach 1: plain Get (single call, may hit 50k cap) ─────────────────
    print("[1] api.get('ExceptionEvent', search={fromDate, toDate, ruleSearch})")
    try:
        get_events = api.get(
            "ExceptionEvent",
            search={"fromDate": from_dt, "toDate": to_dt, "ruleSearch": {"id": rule_id}},
            resultsLimit=50_000,
        )
        get_count = len(get_events)
        get_unique = len({e.get("id") for e in get_events if e.get("id")})
        af_months = Counter(af_month(e) for e in get_events)
        print(f"    rows={get_count}  unique_ids={get_unique}")
        print(f"    activeFrom by month: {dict(sorted(af_months.items()))}")
        if get_count >= 50_000:
            print("    WARNING: hit resultsLimit cap (50k) — single-call result is truncated")
    except Exception as exc:
        print(f"    FAILED: {exc!r}")
        get_count, get_unique = None, None
    print()

    # ── Approach 2: GetFeed cursor ───────────────────────────────────────────
    print("[2] api.call('GetFeed', typeName='ExceptionEvent', ...) with cursor")
    feed_all: list[dict] = []
    from_version: str | None = None
    page_count = 0
    try:
        while True:
            kwargs = {
                "typeName": "ExceptionEvent",
                "search": {"fromDate": from_dt, "toDate": to_dt, "ruleSearch": {"id": rule_id}},
                "resultsLimit": 50_000,
            }
            if from_version:
                kwargs["fromVersion"] = from_version
            feed = api.call("GetFeed", **kwargs)
            data = feed.get("data", []) if isinstance(feed, dict) else []
            page_count += 1
            feed_all.extend(data)
            next_version = feed.get("toVersion") if isinstance(feed, dict) else None
            print(f"    page {page_count}: rows={len(data)} toVersion={next_version}")
            if not data or not next_version or next_version == from_version or len(data) < 50_000:
                break
            from_version = next_version

        feed_count = len(feed_all)
        feed_unique = len({e.get("id") for e in feed_all if e.get("id")})
        af_months = Counter(af_month(e) for e in feed_all)
        # Count events whose activeFrom is strictly outside the requested window
        out_of_window = 0
        for e in feed_all:
            af = e.get("activeFrom")
            if isinstance(af, datetime):
                if af.date() < from_date or af.date() > to_date:
                    out_of_window += 1
        print(f"    total rows={feed_count}  unique_ids={feed_unique}")
        print(f"    activeFrom by month: {dict(sorted(af_months.items()))}")
        print(f"    events with activeFrom OUTSIDE [{from_date}..{to_date}]: {out_of_window}")
    except Exception as exc:
        print(f"    FAILED: {exc!r}")
        feed_count, feed_unique = None, None
    print()

    # ── Approach 3: date-chunked Get (split window into day buckets) ─────────
    print("[3] date-chunked api.get('ExceptionEvent', ...) — one call per day")
    chunked_all: list[dict] = []
    chunked_caps_hit = 0
    try:
        cur = from_date
        while cur <= to_date:
            d_from = datetime.combine(cur, datetime.min.time()).isoformat()
            d_to = datetime.combine(cur, datetime.max.time()).isoformat()
            day_evs = api.get(
                "ExceptionEvent",
                search={"fromDate": d_from, "toDate": d_to, "ruleSearch": {"id": rule_id}},
                resultsLimit=50_000,
            )
            chunked_all.extend(day_evs)
            if len(day_evs) >= 50_000:
                chunked_caps_hit += 1
                print(f"    {cur}: rows={len(day_evs)}  WARNING hit 50k cap on a single day")
            cur += timedelta(days=1)
        chunked_count = len(chunked_all)
        chunked_unique = len({e.get("id") for e in chunked_all if e.get("id")})
        af_months = Counter(af_month(e) for e in chunked_all)
        print(f"    total rows={chunked_count}  unique_ids={chunked_unique}  days_with_cap={chunked_caps_hit}")
        print(f"    activeFrom by month: {dict(sorted(af_months.items()))}")
    except Exception as exc:
        print(f"    FAILED: {exc!r}")
        chunked_count, chunked_unique = None, None
    print()

    # ── Approach 4: GetReportData (Advanced Exceptions Summary) ──────────────
    print("[4] api.call('GetReportData', argument=ReportTypedArgument)")
    report_arg = {
        "templateId": "ReportTemplateAdvancedExceptionsSummaryId",
        "reportArgumentType": "ExceptionsSummary",
        "fromDate": from_dt,
        "toDate": to_dt,
        "includeAllChildren": True,
        "ruleSearch": {"id": rule_id},
    }
    try:
        report = api.call("GetReportData", argument=report_arg)
        print(f"    raw response type: {type(report).__name__}")
        print(f"    raw response (first 800 chars): {json.dumps(report, default=str)[:800]}")
    except Exception as exc:
        print(f"    FAILED: {exc!r}")
    print()

    # ── Summary ──────────────────────────────────────────────────────────────
    print("-" * 60)
    print(f"Get (single, capped 50k):  count={get_count}     unique_ids={get_unique}")
    print(f"GetFeed (cursor):          count={feed_count}    unique_ids={feed_unique}")
    print(f"Get (chunked by day):      count={chunked_count} unique_ids={chunked_unique}")
    print("(compare against UI Excel ground truth)")


if __name__ == "__main__":
    main()
