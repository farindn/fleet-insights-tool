"""Fleet data routers: groups, rules, fuel types."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.routers.deps import get_credentials
from app.schemas.fleet import (
    AvailableRulesResponse,
    FuelTypeListResponse,
    GroupListResponse,
    RuleListResponse,
)
from app.services.analytics.fleet import (
    aggregate_fuel_type_counts,
    detect_fuel_types,
    discover_customers,
    get_devices_in_group,
)
from app.services.geotab import GeotabClient

import asyncio

router = APIRouter()


@router.get("/api/groups", response_model=GroupListResponse)
async def list_groups(creds: dict = Depends(get_credentials)):
    """Return selectable customer groups as a flat list."""
    client = GeotabClient.from_credentials(creds)
    await client.authenticate()
    devices, groups = await asyncio.gather(client.get_devices(), client.get_groups())
    customers = discover_customers(groups, devices)
    items = sorted(customers.values(), key=lambda g: g["name"].lower())
    return GroupListResponse(groups=items)


@router.get("/api/rules", response_model=RuleListResponse)
async def list_rules(
    rule_ids: str = Query(..., description="Comma-separated rule IDs"),
    creds: dict = Depends(get_credentials),
):
    """Resolve a comma-separated list of rule IDs to their names.

    Returns one entry per requested id with its ``name`` and a ``found`` flag
    (False when the rule does not exist in the database). Used to validate/label
    the safety scorecard rules (see USER_GUIDE.md "Safety Scorecard Rules").
    """
    client = GeotabClient.from_credentials(creds)
    await client.authenticate()
    ids = [r.strip() for r in rule_ids.split(",") if r.strip()]
    items = []
    for rid in ids:
        rule = await client.get_rule(rid)
        items.append({
            "id": rid,
            "name": rule.get("name") if rule else None,
            "found": rule is not None,
        })
    return RuleListResponse(rules=items)


@router.get("/api/rules/all", response_model=AvailableRulesResponse)
async def list_all_rules(creds: dict = Depends(get_credentials)):
    """Get all available rules in the database for dropdown selection."""
    client = GeotabClient.from_credentials(creds)
    await client.authenticate()
    all_rules = await client.get_all_rules()
    items = [
        {"id": r.get("id", ""), "name": r.get("name", "Unnamed Rule")}
        for r in all_rules
        if r.get("id") and r.get("name")
    ]
    # Sort by name for easier selection
    items.sort(key=lambda x: x["name"].lower())
    return AvailableRulesResponse(rules=items)


@router.get("/api/fuel-types", response_model=FuelTypeListResponse)
async def list_fuel_types(
    group_id: str = Query(...),
    creds: dict = Depends(get_credentials),
):
    """Detect the fuel types present in a group and their default fuel/idle rates.

    Powers the Fuel & Idling Settings table (see USER_GUIDE.md "Configuring a
    Report" → "Fuel & Idling Settings"): one row per detected fuel type with a
    vehicle count and editable default price/idle rate, plus the count and list
    of vehicles whose powertrain could not be resolved.
    """
    client = GeotabClient.from_credentials(creds)
    await client.authenticate()
    devices, groups = await asyncio.gather(client.get_devices(), client.get_groups())
    group_devices = get_devices_in_group(group_id, devices, groups)
    if not group_devices:
        raise HTTPException(status_code=404, detail="No devices found for this group")
    device_fuel_map = detect_fuel_types(group_devices, groups)
    aggregated = aggregate_fuel_type_counts(group_devices, device_fuel_map)

    # Build the "configured" rows: keep every detected fuel type, skipping the
    # synthetic "unknown" bucket (those vehicles are reported separately below).
    # The internal analytics fields price_per_unit / idle_rate are remapped to the
    # API's default_price / default_idle_rate names — they seed the editable
    # Price/Unit and Idle Rate inputs the user can override in the UI.
    items = []
    for ft in aggregated:
        if ft["group_id"] == "unknown":
            continue
        items.append({
            "group_id": ft["group_id"],
            "label": ft["label"],
            "powertrain": ft["powertrain"],
            "vehicle_count": ft["vehicle_count"],
            "default_price": ft["price_per_unit"],
            "price_unit": ft["price_unit"],
            "idle_unit": ft["idle_unit"],
            "default_idle_rate": ft["idle_rate"],
        })

    # The other side of the split: vehicles with no valid powertrain assignment
    # (fuel type "unknown"). These are surfaced so the UI can warn the user; they
    # are excluded from idling-cost calculations until fixed in MyGeotab.
    unconfigured = []
    for dev in group_devices:
        dev_id = dev.get("id", "")
        meta = device_fuel_map.get(dev_id) or {}
        if meta.get("group_id") == "unknown":
            unconfigured.append({
                "id": dev_id,
                "name": dev.get("name") or dev_id,
                "serial": dev.get("serialNumber"),
            })

    return FuelTypeListResponse(
        fuel_types=items,
        total_vehicles=len(group_devices),
        unconfigured_count=len(unconfigured),
        unconfigured_vehicles=unconfigured,
    )
