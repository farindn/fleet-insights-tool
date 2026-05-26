"""Idling cost analytics: compute per-device idle cost using fuel type settings."""
from __future__ import annotations

import pandas as pd


def compute_idling(
    trips_df: pd.DataFrame,
    device_fuel_map: dict[str, dict],
    fuel_settings: list[dict],
) -> pd.DataFrame:
    """
    Compute per-device idle hours and cost.

    fuel_settings: list of {group_id, label, price_per_unit, idle_rate, price_unit}
                   These come from the user's request (GenerateRequest.fuel_settings).
    device_fuel_map: {device_id: {group_id, label, price_per_unit, idle_rate, ...}}
                     from detect_fuel_types().

    Returns DataFrame: device_id, idle_hours, fuel_group_id, fuel_label,
                       idle_rate, price_per_unit, price_unit, idle_cost.
    """
    # Build lookup from group_id → user-provided settings (overrides defaults)
    user_settings: dict[str, dict] = {fs["group_id"]: fs for fs in fuel_settings}

    if trips_df.empty:
        return pd.DataFrame(columns=[
            "device_id", "idle_hours", "fuel_group_id", "fuel_label",
            "idle_rate", "price_per_unit", "price_unit", "idle_cost"
        ])

    # Sum idle hours per device
    idle_totals = (
        trips_df.groupby("device_id")["idle_hours"]
        .sum()
        .reset_index()
        .rename(columns={"idle_hours": "idle_hours"})
    )

    rows = []
    for _, row in idle_totals.iterrows():
        dev_id = row["device_id"]
        idle_h = row["idle_hours"]

        # Get fuel metadata for this device
        fuel_meta = device_fuel_map.get(dev_id, {})
        group_id = fuel_meta.get("group_id", "unknown")

        # Skip vehicles without a configured fuel type (idle cost excluded)
        if group_id == "unknown":
            continue

        # User-provided settings take priority over detected defaults
        if group_id in user_settings:
            settings = user_settings[group_id]
            idle_rate = settings["idle_rate"]
            price_per_unit = settings["price_per_unit"]
            price_unit = settings["price_unit"]
        else:
            idle_rate = fuel_meta.get("idle_rate", 2.5)
            price_per_unit = fuel_meta.get("price_per_unit", 2.15)
            price_unit = fuel_meta.get("price_unit", "/L")

        idle_cost = idle_h * idle_rate * price_per_unit

        rows.append({
            "device_id": dev_id,
            "idle_hours": round(idle_h, 2),
            "fuel_group_id": group_id,
            "fuel_label": fuel_meta.get("label", "Unknown"),
            "idle_rate": idle_rate,
            "price_per_unit": price_per_unit,
            "price_unit": price_unit,
            "idle_cost": round(idle_cost, 2),
        })

    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=[
        "device_id", "idle_hours", "fuel_group_id", "fuel_label",
        "idle_rate", "price_per_unit", "price_unit", "idle_cost"
    ])
