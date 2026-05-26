"""At-risk vehicle identification: 5-factor matrix."""
from __future__ import annotations

import pandas as pd

from app.config import settings


def compute_at_risk(
    utilization_df: pd.DataFrame,
    idling_df: pd.DataFrame,
    safety_df: pd.DataFrame,
    device_names: dict[str, str],
    dormant_days_threshold: int | None = None,
) -> pd.DataFrame:
    """
    Identify at-risk vehicles using a 5-flag matrix.

    Flags:
    1. low_utilization  — composite_score < 20
    2. dormant          — active_days < dormant_days_threshold
    3. high_idling      — idle_hours in top 25% (IQR)
    4. low_safety       — safety_score < SAFETY_HIGH_RISK
    5. high_cost        — idle_cost in top 25%

    Returns DataFrame: device_id, name, flags (list[str]), flag_count, risk_level.
    risk_level: "Critical" (≥3 flags), "Warning" (2), "Monitor" (1), "OK" (0).
    """
    if dormant_days_threshold is None:
        dormant_days_threshold = settings.DORMANT_DAYS_THRESHOLD

    # Merge all data sources on device_id
    df = utilization_df[["device_id", "active_days", "composite_score"]].copy()

    if not idling_df.empty:
        df = df.merge(idling_df[["device_id", "idle_hours", "idle_cost"]], on="device_id", how="left")
    else:
        df["idle_hours"] = 0.0
        df["idle_cost"] = 0.0

    if not safety_df.empty:
        df = df.merge(safety_df[["device_id", "safety_score"]], on="device_id", how="left")
    else:
        df["safety_score"] = float("nan")

    df["idle_hours"] = df["idle_hours"].fillna(0.0)
    df["idle_cost"] = df["idle_cost"].fillna(0.0)

    # IQR thresholds for idling
    idle_q75 = df["idle_hours"].quantile(0.75) if len(df) > 0 else 0
    cost_q75 = df["idle_cost"].quantile(0.75) if len(df) > 0 else 0

    rows = []
    for _, row in df.iterrows():
        dev_id = row["device_id"]
        flags: list[str] = []

        if row.get("composite_score", 100) < 20:
            flags.append("low_utilization")

        if row.get("active_days", 999) < dormant_days_threshold:
            flags.append("dormant")

        if row.get("idle_hours", 0) > idle_q75 and idle_q75 > 0:
            flags.append("high_idling")

        safety = row.get("safety_score")
        if safety is not None and not (safety != safety):  # not NaN
            if safety < settings.SAFETY_HIGH_RISK:
                flags.append("low_safety")

        if row.get("idle_cost", 0) > cost_q75 and cost_q75 > 0:
            flags.append("high_cost")

        flag_count = len(flags)
        if flag_count >= 3:
            risk_level = "Critical"
        elif flag_count == 2:
            risk_level = "Warning"
        elif flag_count == 1:
            risk_level = "Monitor"
        else:
            risk_level = "OK"

        rows.append({
            "device_id": dev_id,
            "name": device_names.get(dev_id, dev_id),
            "flags": flags,
            "flag_count": flag_count,
            "risk_level": risk_level,
            "composite_score": row.get("composite_score", 0),
            "safety_score": safety,
            "idle_hours": row.get("idle_hours", 0),
            "idle_cost": row.get("idle_cost", 0),
            "active_days": row.get("active_days", 0),
        })

    result = pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["device_id", "name", "flags", "flag_count", "risk_level",
                 "composite_score", "safety_score", "idle_hours", "idle_cost", "active_days"]
    )

    # Sort: Critical first, then Warning, then Monitor, then OK
    order = {"Critical": 0, "Warning": 1, "Monitor": 2, "OK": 3}
    if not result.empty:
        result["_sort"] = result["risk_level"].map(order)
        result = result.sort_values("_sort").drop(columns=["_sort"]).reset_index(drop=True)

    return result
