"""Safety score analytics: event-rate scoring with seatbelt hybrid variant."""
from __future__ import annotations

import math

import pandas as pd


def get_multiplier(count: int) -> float:
    """Severity multiplier that escalates the penalty as event volume rises.

    Repeated violations weigh more heavily: the larger a vehicle's event
    count, the bigger the multiplier applied to its event rate in
    ``event_count_score``. The multiplier steps up at the 5 / 15 / 30 / 50
    event breakpoints:

        count == 0        -> 1.0   (no events)
        1  <= count <= 5  -> 1.0
        6  <= count <= 15 -> 1.1
        16 <= count <= 30 -> 1.2
        31 <= count <= 50 -> 1.35
        count > 50        -> 1.5

    See USER_GUIDE.md -> Understanding the Calculations -> Safety Score.
    """
    if count == 0:
        return 1.0
    if count <= 5:
        return 1.0
    if count <= 15:
        return 1.1
    if count <= 30:
        return 1.2
    if count <= 50:
        return 1.35
    return 1.5


def event_count_score(event_count: int, distance_km: float) -> float:
    """
    Score = 100 − (events_per_1000km × multiplier × 10), clipped 0–100.
    Returns NaN if distance is 0.
    """
    if distance_km <= 0:
        return float("nan")
    rate = event_count / distance_km * 1000
    multiplier = get_multiplier(event_count)
    score = 100 - rate * multiplier * 10
    return max(0.0, min(100.0, score))


def seatbelt_pct_distance_score(
    seatbelt_events: int,
    distance_without_belt_km: float,
    total_distance_km: float,
) -> float:
    """
    Hybrid seatbelt score: 0.3 × event_count_score + 0.7 × distance_pct_score.
    distance_pct_score = 100 × (1 − distance_without_belt_km / total_distance_km).
    Returns NaN if total_distance_km is 0.
    """
    if total_distance_km <= 0:
        return float("nan")

    cnt_score = event_count_score(seatbelt_events, total_distance_km)
    pct_score = 100.0 * (1 - distance_without_belt_km / total_distance_km)
    pct_score = max(0.0, min(100.0, pct_score))

    if math.isnan(cnt_score):
        return pct_score
    return 0.3 * cnt_score + 0.7 * pct_score


def compute_safety_scores(
    exception_events: dict[str, list[dict]],
    safety_rules: list[dict],
    rule_names: dict[str, str],
    trips_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute per-device safety scores.

    Parameters
    ----------
    exception_events : {rule_id: [event_dict, ...]}
    safety_rules     : [{"rule_id": str, "weight": float}, ...]  (weights sum ~100)
    rule_names       : {rule_id: display_name}
    trips_df         : output of build_trips_dataframe()

    Returns
    -------
    DataFrame with columns: device_id, safety_score, {rule_id}_score for each rule.
    """
    if trips_df.empty:
        return pd.DataFrame(columns=["device_id", "safety_score"])

    # Per-device total distance and seatbelt distances
    dist_df = trips_df.groupby("device_id").agg(
        total_distance_km=("distance_km", "sum"),
    ).reset_index()

    device_ids = set(dist_df["device_id"].tolist())

    # Normalize weights → sum to 1.0
    total_weight = sum(r["weight"] for r in safety_rules)
    if total_weight <= 0:
        total_weight = 1.0

    # Count events per device per rule
    rule_event_counts: dict[str, dict[str, int]] = {}
    for rule in safety_rules:
        rid = rule["rule_id"]
        events = exception_events.get(rid, [])
        counts: dict[str, int] = {}
        for ev in events:
            dev = ev.get("device", {})
            dev_id = dev.get("id") if isinstance(dev, dict) else dev
            if dev_id:
                counts[dev_id] = counts.get(dev_id, 0) + 1
        rule_event_counts[rid] = counts

    # Seatbelt: distance without seatbelt per device
    seatbelt_dist_by_device: dict[str, float] = {}
    for rule in safety_rules:
        rid = rule["rule_id"]
        name = rule_names.get(rid, "")
        if "seatbelt" in name.lower():
            events = exception_events.get(rid, [])
            for ev in events:
                dev = ev.get("device", {})
                dev_id = dev.get("id") if isinstance(dev, dict) else dev
                # ExceptionEvent.distance is reported in metres; convert to km
                dist = (ev.get("distance") or 0) / 1000.0
                if dev_id:
                    seatbelt_dist_by_device[dev_id] = seatbelt_dist_by_device.get(dev_id, 0) + dist
            break  # only first seatbelt rule

    rows = []
    for _, dr in dist_df.iterrows():
        dev_id = dr["device_id"]
        total_dist = dr["total_distance_km"]

        rule_scores: dict[str, float] = {}
        weighted_sum = 0.0
        weight_used = 0.0

        for rule in safety_rules:
            rid = rule["rule_id"]
            w = rule["weight"] / total_weight
            name = rule_names.get(rid, "")
            count = rule_event_counts.get(rid, {}).get(dev_id, 0)

            if "seatbelt" in name.lower():
                dist_no_belt = seatbelt_dist_by_device.get(dev_id, 0.0)
                score = seatbelt_pct_distance_score(count, dist_no_belt, total_dist)
            else:
                score = event_count_score(count, total_dist)

            rule_scores[f"{rid}_score"] = score
            if not math.isnan(score):
                weighted_sum += score * w
                weight_used += w

        # This raw 0-100 safety_score is banded downstream in report_builder.py
        # into High Risk <60 / Medium 60-75 / Mild 75-90 / Low >=90.
        # See USER_GUIDE.md -> Understanding the Calculations -> Safety Score.
        if weight_used > 0:
            safety_score = round(weighted_sum / weight_used, 1)
        else:
            safety_score = float("nan")

        row = {"device_id": dev_id, "safety_score": safety_score}
        row.update(rule_scores)
        rows.append(row)

    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["device_id", "safety_score"])
