"""Utilization analytics: active days, monthly KPIs, composite score, GPS points."""
from __future__ import annotations

from datetime import date, datetime, time as dt_time

import numpy as np
import pandas as pd


# GPS coordinate validity bounds (exclude null island and invalid coords)
# No regional filtering — works for any country
GPS_VALID_LAT_MIN, GPS_VALID_LAT_MAX = -85.0, 85.0
GPS_VALID_LON_MIN, GPS_VALID_LON_MAX = -180.0, 180.0


def parse_duration_hours(duration_val) -> float:
    """Parse duration → hours.

    Handles:
    - datetime.timedelta objects (mygeotab SDK's primary format)
    - datetime.time objects (legacy/fallback)
    - ISO 8601 duration strings like 'PT1H30M45S'
    """
    from datetime import timedelta

    if not duration_val:
        return 0.0
    if isinstance(duration_val, timedelta):
        return duration_val.total_seconds() / 3600
    if isinstance(duration_val, dt_time):
        return duration_val.hour + duration_val.minute / 60 + duration_val.second / 3600
    import re
    pattern = r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?"
    m = re.match(pattern, str(duration_val))
    if not m:
        return 0.0
    days = float(m.group(1) or 0)
    hours = float(m.group(2) or 0)
    minutes = float(m.group(3) or 0)
    seconds = float(m.group(4) or 0)
    return days * 24 + hours + minutes / 60 + seconds / 3600


def _parse_dt(val) -> datetime | None:
    """Accept either a datetime object (mygeotab SDK) or an ISO string."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def build_trips_dataframe(
    trips: list[dict],
    device_ids: set[str],
    start_date: date | None = None,
    end_date: date | None = None,
) -> pd.DataFrame:
    """Convert raw trip dicts to a clean DataFrame filtered to device_ids.

    When start_date/end_date are provided, trips whose start timestamp falls
    outside [start_date, end_date] are excluded. This prevents trips that
    started before the analysis period (but ended within it) from appearing
    in monthly charts.
    """
    rows = []
    for t in trips:
        dev = t.get("device", {})
        dev_id = dev.get("id") if isinstance(dev, dict) else dev
        if dev_id not in device_ids:
            continue

        start_dt = _parse_dt(t.get("start") or t.get("startDateTime"))
        stop_dt = _parse_dt(t.get("stop") or t.get("stopDateTime"))

        # Filter out trips whose start is outside the requested analysis window
        if start_dt:
            trip_date = start_dt.date()
            if start_date and trip_date < start_date:
                continue
            if end_date and trip_date > end_date:
                continue

        distance_km = t.get("distance") or 0.0  # MyGeotab Trip.distance is already in km
        drive_hours = parse_duration_hours(t.get("drivingDuration"))
        idle_hours = parse_duration_hours(t.get("idlingDuration"))

        rows.append({
            "device_id": dev_id,
            "start": start_dt,
            "stop": stop_dt,
            "date": start_dt.date() if start_dt else None,
            "month": start_dt.strftime("%Y-%m") if start_dt else None,
            "distance_km": distance_km,
            "drive_hours": drive_hours,
            "idle_hours": idle_hours,
            "max_speed": t.get("maximumSpeed") or 0.0,
            "stop_lat": t.get("stopPoint", {}).get("y") if isinstance(t.get("stopPoint"), dict) else None,
            "stop_lon": t.get("stopPoint", {}).get("x") if isinstance(t.get("stopPoint"), dict) else None,
        })

    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["device_id", "start", "stop", "date", "month",
                 "distance_km", "drive_hours", "idle_hours", "max_speed", "stop_lat", "stop_lon"]
    )


def compute_active_days(trips_df: pd.DataFrame, device_ids: set[str], start_date: date, end_date: date) -> pd.DataFrame:
    """
    Returns DataFrame with columns: device_id, active_days, total_days, utilization_pct.
    total_days = number of calendar days in [start_date, end_date].
    """
    total_days = (end_date - start_date).days + 1

    if trips_df.empty:
        records = [{"device_id": did, "active_days": 0, "total_days": total_days, "utilization_pct": 0.0}
                   for did in device_ids]
        return pd.DataFrame(records)

    active = (
        trips_df.dropna(subset=["date"])
        .groupby("device_id")["date"]
        .nunique()
        .reset_index()
        .rename(columns={"date": "active_days"})
    )

    result = pd.DataFrame({"device_id": list(device_ids)})
    result = result.merge(active, on="device_id", how="left")
    result["active_days"] = result["active_days"].fillna(0).astype(int)
    result["total_days"] = total_days
    result["utilization_pct"] = (result["active_days"] / total_days * 100).clip(0, 100)
    return result


def compute_monthly_kpis(trips_df: pd.DataFrame) -> pd.DataFrame:
    """
    Returns monthly aggregation per device:
    device_id, month, distance_km, drive_hours, idle_hours, trip_count.
    """
    if trips_df.empty:
        return pd.DataFrame(columns=["device_id", "month", "distance_km", "drive_hours", "idle_hours", "trip_count"])

    grouped = (
        trips_df.dropna(subset=["month"])
        .groupby(["device_id", "month"])
        .agg(
            distance_km=("distance_km", "sum"),
            drive_hours=("drive_hours", "sum"),
            idle_hours=("idle_hours", "sum"),
            trip_count=("distance_km", "count"),
        )
        .reset_index()
    )
    return grouped


def compute_utilization_composite(active_df: pd.DataFrame, trips_df: pd.DataFrame) -> pd.DataFrame:
    """
    Composite utilization score 0–100 using IQR-based bucketing of distance + active days.
    Returns active_df enriched with: total_distance_km, total_drive_hours, total_idle_hours,
    trip_count, composite_score, tier.
    """
    if trips_df.empty:
        active_df["total_distance_km"] = 0.0
        active_df["total_drive_hours"] = 0.0
        active_df["total_idle_hours"] = 0.0
        active_df["trip_count"] = 0
        active_df["composite_score"] = 0.0
        active_df["tier"] = "Dormant"
        return active_df

    totals = trips_df.groupby("device_id").agg(
        total_distance_km=("distance_km", "sum"),
        total_drive_hours=("drive_hours", "sum"),
        total_idle_hours=("idle_hours", "sum"),
        trip_count=("distance_km", "count"),
    ).reset_index()

    df = active_df.merge(totals, on="device_id", how="left")
    df["total_distance_km"] = df["total_distance_km"].fillna(0.0)
    df["total_drive_hours"] = df["total_drive_hours"].fillna(0.0)
    df["total_idle_hours"] = df["total_idle_hours"].fillna(0.0)
    df["trip_count"] = df["trip_count"].fillna(0).astype(int)

    def iqr_score(series: pd.Series) -> pd.Series:
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        clipped = series.clip(lower=max(lo, 0), upper=hi)
        span = clipped.max() - clipped.min()
        if span == 0:
            return pd.Series(np.zeros(len(series)), index=series.index)
        return (clipped - clipped.min()) / span * 100

    dist_score = iqr_score(df["total_distance_km"])
    days_score = iqr_score(df["utilization_pct"])
    df["composite_score"] = (0.6 * dist_score + 0.4 * days_score).clip(0, 100).round(1)

    def assign_tier(score: float) -> str:
        if score >= 75:
            return "High"
        if score >= 40:
            return "Moderate"
        if score > 0:
            return "Low"
        return "Dormant"

    df["tier"] = df["composite_score"].apply(assign_tier)
    return df


def compute_max_speeding(trips_df: pd.DataFrame, device_names: dict[str, str], top_n: int = 15) -> pd.DataFrame:
    """
    Compute top N vehicles by maximum speed recorded across all trips.
    Returns DataFrame: device_id, device_name, max_speed (km/h).
    """
    if trips_df.empty or "max_speed" not in trips_df.columns:
        return pd.DataFrame(columns=["device_id", "device_name", "max_speed"])

    max_speeds = (
        trips_df.groupby("device_id")["max_speed"]
        .max()
        .reset_index()
        .rename(columns={"max_speed": "max_speed"})
    )
    max_speeds = max_speeds[max_speeds["max_speed"] > 0]
    max_speeds = max_speeds.sort_values("max_speed", ascending=False).head(top_n)
    max_speeds["device_name"] = max_speeds["device_id"].map(device_names).fillna(max_speeds["device_id"])
    return max_speeds[["device_id", "device_name", "max_speed"]]


def extract_gps_points(trips_df: pd.DataFrame) -> list[list[float]]:
    """
    Extract [lat, lon] stop points from trips.
    Returns all valid GPS points (one per trip), excluding null island (0,0)
    and coordinates outside valid bounds.
    """
    if trips_df.empty:
        return []

    pts = trips_df.dropna(subset=["stop_lat", "stop_lon"])

    # Exclude null island (0,0) and invalid coordinates
    pts = pts[
        (pts["stop_lat"] >= GPS_VALID_LAT_MIN) & (pts["stop_lat"] <= GPS_VALID_LAT_MAX) &
        (pts["stop_lon"] >= GPS_VALID_LON_MIN) & (pts["stop_lon"] <= GPS_VALID_LON_MAX) &
        ~((pts["stop_lat"].abs() < 0.01) & (pts["stop_lon"].abs() < 0.01))  # exclude null island
    ]

    pairs = pts[["stop_lat", "stop_lon"]].values.tolist()
    return [[round(lat, 6), round(lon, 6)] for lat, lon in pairs]
