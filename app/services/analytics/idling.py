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

    fuel_settings: list of {group_id, label, price_per_unit, idle_rate, price_unit,
                   price_per_unit_elec?, idle_rate_elec?}. These come from the
                   user's request (GenerateRequest.fuel_settings).
    device_fuel_map: {device_id: {group_id, label, price_per_unit, idle_rate,
                     idle_unit, price_per_unit_elec?, idle_rate_elec?, ...}}
                     from detect_fuel_types().

    Cost model (mirrors the Idling ROI reference tool):
      • Single-fuel powertrains: idle_cost = idle_hours × idle_rate × price_per_unit.
      • PHEV (dual-fuel): idle_cost = liquid (idle_hours × idle_rate × price_per_unit)
        + electric (idle_hours × idle_rate_elec × price_per_unit_elec).
    See USER_GUIDE.md -> Understanding the Calculations -> Idling Cost.

    Returns DataFrame: device_id, idle_hours, fuel_group_id, fuel_label,
                       idle_rate, price_per_unit, price_unit, idle_unit,
                       idle_rate_elec, price_per_unit_elec, idle_cost.
    """
    COLUMNS = [
        "device_id", "idle_hours", "fuel_group_id", "fuel_label",
        "idle_rate", "price_per_unit", "price_unit", "idle_unit",
        "idle_rate_elec", "price_per_unit_elec", "idle_cost",
    ]

    # Build lookup from group_id → user-provided settings (overrides defaults)
    user_settings: dict[str, dict] = {fs["group_id"]: fs for fs in fuel_settings}

    if trips_df.empty:
        return pd.DataFrame(columns=COLUMNS)

    # Sum idle hours per device
    idle_totals = (
        trips_df.groupby("device_id")["idle_hours"]
        .sum()
        .reset_index()
    )

    rows = []
    for _, row in idle_totals.iterrows():
        dev_id = row["device_id"]
        idle_h = row["idle_hours"]

        # Get fuel metadata for this device
        fuel_meta = device_fuel_map.get(dev_id, {})
        group_id = fuel_meta.get("group_id", "unknown")

        # Vehicles with no valid powertrain (group_id == "unknown") are excluded
        # from idle COST here. Their idle HOURS are still counted elsewhere
        # (the utilization trip aggregation) — only cost attribution is skipped.
        # See USER_GUIDE.md -> Understanding the Calculations -> Idling Cost.
        if group_id == "unknown":
            continue

        # User-provided settings take priority over detected defaults.
        if group_id in user_settings:
            settings = user_settings[group_id]
            idle_rate = settings["idle_rate"]
            price_per_unit = settings["price_per_unit"]
            price_unit = settings["price_unit"]
            idle_rate_elec = settings.get("idle_rate_elec")
            price_per_unit_elec = settings.get("price_per_unit_elec")
        else:
            # Edge-case fallback: the device is in a known powertrain group but
            # its fuel metadata is incomplete. Fall back to generic diesel-like
            # constants (idle_rate 2.5, price 2.15, unit "/L") so a cost can
            # still be estimated rather than dropped.
            idle_rate = fuel_meta.get("idle_rate", 2.5)
            price_per_unit = fuel_meta.get("price_per_unit", 2.15)
            price_unit = fuel_meta.get("price_unit", "/L")
            idle_rate_elec = fuel_meta.get("idle_rate_elec")
            price_per_unit_elec = fuel_meta.get("price_per_unit_elec")

        # The idle-rate unit (L/h, kWh/h, kg/h) is a property of the powertrain,
        # not user-editable, so always read it from the detected metadata.
        idle_unit = fuel_meta.get("idle_unit", "L/h")

        # Core idling cost = idle hours × idle rate (units/hour) × price per unit.
        # PHEV is dual-fuel: add the electricity component on top of the liquid
        # one when both electric fields are present.
        # See USER_GUIDE.md -> Understanding the Calculations -> Idling Cost.
        idle_cost = idle_h * idle_rate * price_per_unit
        if idle_rate_elec is not None and price_per_unit_elec is not None:
            idle_cost += idle_h * idle_rate_elec * price_per_unit_elec

        rows.append({
            "device_id": dev_id,
            "idle_hours": round(idle_h, 2),
            "fuel_group_id": group_id,
            "fuel_label": fuel_meta.get("label", "Unknown"),
            "idle_rate": idle_rate,
            "price_per_unit": price_per_unit,
            "price_unit": price_unit,
            "idle_unit": idle_unit,
            "idle_rate_elec": idle_rate_elec,
            "price_per_unit_elec": price_per_unit_elec,
            "idle_cost": round(idle_cost, 2),
        })

    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=COLUMNS)
