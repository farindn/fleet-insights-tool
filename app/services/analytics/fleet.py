"""Fleet discovery and fuel-type detection from MyGeotab groups."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

# MyGeotab returns b-number aliases as parent IDs for system groups.
# Normalise them so subtree traversal by canonical name works correctly.
GROUP_ID_ALIASES: dict[str, str] = {
    "b1": "GroupEverythingId",
    "b2": "GroupCompanyId",
    "b3": "GroupFleetId",
    "b4": "GroupNothingId",
    "b5": "GroupDefectiveId",
    "b6": "GroupDriveId",
}

# Both forms of the company root (alias + canonical)
COMPANY_ROOTS = {"GroupCompanyId", "b2"}

# System group IDs that should never appear in the customer dropdown
SYSTEM_GROUP_IDS = {
    # GroupCompanyId is intentionally NOT here — users can select it
    "GroupFleetId",  "GroupNothingId", "GroupEverythingId",
    "GroupDefectiveId", "GroupDriveId",
    "b1", "b3", "b4", "b5", "b6",
}

SYSTEM_NAME_KEYWORDS = {
    "nothing",
    "everything",
    "defective",
    "drive users",
    "all users",
}

# Subtree roots whose descendants should be excluded from the customer dropdown
# (e.g., asset information groups, driver activity groups)
EXCLUDED_SUBTREE_ROOTS: set[str] = {
    "GroupAssetInformationId",
    "GroupDriverActivityId",
    "GroupUserSupportId",
}

# Maps MyGeotab powertrain/fuel group IDs → (label, price_per_unit, price_unit, idle_rate, idle_unit, powertrain)
# price_unit uses "/ <unit>" format — currency prefix is added by the frontend/report from the user's selection.
# Idle rates sourced from reference_idle_rate_defaults.md (2026-05-15).
# Ordered by specificity: electrified drivetrains first so that a PHEV
# (whose ancestry includes both GroupPluginHybridElectricVehicleId AND
# GroupGasolinePetrolId) is matched as PHEV, not Gasoline.
FUEL_GROUP_MAP: dict[str, dict] = {
    "GroupBatteryElectricVehicleId": {
        "label": "BEV",
        "price_per_unit": 0.546,
        "price_unit": "/kWh",
        "idle_rate": 3.0,
        "idle_unit": "kWh/h",
        "powertrain": "Electric",
    },
    "GroupPluginHybridElectricVehicleId": {
        "label": "PHEV",
        "price_per_unit": 2.05,
        "price_unit": "/L",
        "idle_rate": 0.3,
        "idle_unit": "L/h",
        "powertrain": "Plug-in",
    },
    "GroupFuelCellElectricVehicleId": {
        "label": "FCEV",
        "price_per_unit": 15.0,
        "price_unit": "/kg",
        "idle_rate": 0.3,
        "idle_unit": "kg/h",
        "powertrain": "Fuel Cell",
    },
    "GroupGasolinePetrolId": {
        "label": "Gasoline",
        "price_per_unit": 2.05,
        "price_unit": "/L",
        "idle_rate": 0.6,
        "idle_unit": "L/h",
        "powertrain": "ICE",
    },
    "GroupDieselId": {
        "label": "Diesel",
        "price_per_unit": 2.15,
        "price_unit": "/L",
        "idle_rate": 3.0,
        "idle_unit": "L/h",
        "powertrain": "ICE",
    },
    "GroupBiodieselId": {
        "label": "Biodiesel",
        "price_per_unit": 2.10,
        "price_unit": "/L",
        "idle_rate": 3.0,
        "idle_unit": "L/h",
        "powertrain": "ICE",
    },
    "GroupEthanolId": {
        "label": "Ethanol",
        "price_per_unit": 1.90,
        "price_unit": "/L",
        "idle_rate": 0.7,
        "idle_unit": "L/h",
        "powertrain": "ICE",
    },
    "GroupCompressedNaturalGasId": {
        "label": "CNG",
        "price_per_unit": 1.50,
        "price_unit": "/kg",
        "idle_rate": 1.8,
        "idle_unit": "kg/h",
        "powertrain": "ICE",
    },
    "GroupPropaneLiquifiedPetroleumGasId": {
        "label": "LPG",
        "price_per_unit": 1.80,
        "price_unit": "/L",
        "idle_rate": 2.0,
        "idle_unit": "L/h",
        "powertrain": "ICE",
    },
}

# Fallback fuel type for devices not matched to any fuel group
UNKNOWN_FUEL = {
    "label": "Unknown",
    "price_per_unit": 2.15,
    "price_unit": "/L",
    "idle_rate": 2.5,
    "idle_unit": "L/h",
    "powertrain": "ICE",
    "group_id": "unknown",
}


def build_group_children(groups: list[dict]) -> dict[str, list[str]]:
    """Return {parent_id: [child_id, ...]} from the raw group list.

    Parent IDs are normalized using GROUP_ID_ALIASES so that b2 → GroupCompanyId, etc.
    """
    children: dict[str, list[str]] = defaultdict(list)
    for g in groups:
        parent = g.get("parent", {})
        if parent:
            pid = parent.get("id") if isinstance(parent, dict) else parent
            if pid:
                # Normalize alias to canonical ID
                pid = GROUP_ID_ALIASES.get(pid, pid)
                children[pid].append(g["id"])
    return dict(children)


def get_subtree_group_ids(root_id: str, children: dict[str, list[str]]) -> set[str]:
    """BFS from root_id to collect all descendant group IDs (inclusive)."""
    visited: set[str] = set()
    queue = [root_id]
    while queue:
        node = queue.pop()
        if node in visited:
            continue
        visited.add(node)
        queue.extend(children.get(node, []))
    return visited


def discover_customers(groups: list[dict], devices: list[dict]) -> dict[str, dict]:
    """
    Return {group_id: {id, name, vehicle_count}} for selectable customer groups.

    - GroupCompanyId is included (users may select the whole fleet).
    - Descendants of EXCLUDED_SUBTREE_ROOTS (asset info, driver activity) are hidden.
    - Devices with no sub-group assignment are handled as UNASSIGNED by the caller.
    """
    children = build_group_children(groups)

    # Build the full set of group IDs that belong to excluded subtrees
    excluded_ids: set[str] = set()
    for root in EXCLUDED_SUBTREE_ROOTS:
        excluded_ids |= get_subtree_group_ids(root, children)

    # Build device → group membership
    device_groups: dict[str, set[str]] = {}
    for dev in devices:
        dev_id = dev.get("id", "")
        glist = dev.get("groups", [])
        g_ids: set[str] = set()
        for g in glist:
            gid = g.get("id") if isinstance(g, dict) else g
            if gid:
                g_ids.add(gid)
        device_groups[dev_id] = g_ids

    customers: dict[str, dict] = {}
    for g in groups:
        gid = g["id"]
        name = (g.get("name") or "").strip()

        # Skip hard-excluded system groups (GroupCompanyId is NOT in this set)
        if gid in SYSTEM_GROUP_IDS:
            continue

        # Skip anything under the excluded subtrees (assets, drivers hierarchy)
        if gid in excluded_ids:
            continue

        # Skip by name keywords (not applied to GroupCompanyId so it always appears)
        if gid != "GroupCompanyId" and any(kw in name.lower() for kw in SYSTEM_NAME_KEYWORDS):
            continue

        # Count devices in this group's subtree.
        # GroupCompanyId is the database root — every device belongs to it implicitly.
        if gid in COMPANY_ROOTS:
            count = len(devices)
        else:
            subtree = get_subtree_group_ids(gid, children)
            count = sum(1 for dev_gs in device_groups.values() if dev_gs & subtree)

        # Always include GroupCompanyId; only include others if they have vehicles
        if gid == "GroupCompanyId" or count > 0:
            customers[gid] = {"id": gid, "name": name, "vehicle_count": count}

    return customers


def build_group_tree(groups: list[dict], devices: list[dict]) -> list[dict]:
    """
    Build a hierarchical group tree similar to MyGeotab's group selector.
    Returns a flat list with hierarchy info for frontend rendering.
    """
    # Build children map with normalized parent IDs
    children: dict[str, list[str]] = defaultdict(list)
    group_map: dict[str, dict] = {}

    for g in groups:
        gid = g["id"]
        parent = g.get("parent", {})
        parent_id = None
        if parent:
            parent_id = parent.get("id") if isinstance(parent, dict) else parent
            # Normalize aliases (b2 -> GroupCompanyId, etc.)
            parent_id = GROUP_ID_ALIASES.get(parent_id, parent_id)

        group_map[gid] = {
            "id": gid,
            "name": (g.get("name") or "").strip(),
            "parent_id": parent_id,
        }

        if parent_id:
            children[parent_id].append(gid)

    # Build device → group membership for vehicle counts
    device_groups: dict[str, set[str]] = {}
    for dev in devices:
        dev_id = dev.get("id", "")
        glist = dev.get("groups", [])
        g_ids: set[str] = set()
        for g in glist:
            gid = g.get("id") if isinstance(g, dict) else g
            if gid:
                g_ids.add(gid)
        device_groups[dev_id] = g_ids

    # Calculate vehicle counts for each group (including subtree)
    def count_vehicles(gid: str) -> int:
        subtree = get_subtree_group_ids(gid, children)
        return sum(1 for dev_gs in device_groups.values() if dev_gs & subtree)

    # Groups to exclude from the tree (system/internal groups)
    HIDDEN_GROUP_IDS = {
        "GroupNothingId", "GroupEverythingId", "GroupDefectiveId",
        "GroupDriveId", "GroupAssetInformationId", "GroupDriverActivityId",
        "GroupUserSupportId",
        "b1", "b3", "b4", "b5", "b6",  # Aliases except b2 (CompanyGroup)
    }

    # Build tree structure starting from GroupCompanyId
    result: list[dict] = []

    def add_group_and_children(gid: str, level: int):
        if gid not in group_map:
            return
        if gid in HIDDEN_GROUP_IDS:
            return

        g = group_map[gid]
        name = g["name"]

        # Skip groups with certain keywords (but not the root)
        if level > 0 and any(kw in name.lower() for kw in SYSTEM_NAME_KEYWORDS):
            return

        child_ids = children.get(gid, [])

        # Get valid children (will be added recursively)
        valid_children = [
            cid for cid in child_ids
            if cid not in HIDDEN_GROUP_IDS
            and cid in group_map
        ]

        vehicle_count = count_vehicles(gid)

        result.append({
            "id": gid,
            "name": name or "Company",
            "parent_id": g["parent_id"],
            "level": level,
            "has_children": len(valid_children) > 0,
            "vehicle_count": vehicle_count,
        })

        # Sort children by name and recurse
        sorted_children = sorted(valid_children, key=lambda cid: group_map[cid]["name"].lower())
        for child_id in sorted_children:
            add_group_and_children(child_id, level + 1)

    # Start from GroupCompanyId (the root company group)
    if "GroupCompanyId" in group_map:
        add_group_and_children("GroupCompanyId", 0)
    # Also try b2 alias if GroupCompanyId not found
    elif "b2" in group_map:
        add_group_and_children("b2", 0)

    return result


def get_devices_in_group(
    group_id: str,
    devices: list[dict],
    groups: list[dict],
) -> list[dict]:
    """Return devices whose group membership intersects the subtree of group_id.

    Special case: GroupCompanyId (or its alias b2) is the database root in MyGeotab,
    and every device implicitly belongs to it — return all devices.
    """
    if group_id in COMPANY_ROOTS:
        return list(devices)

    children = build_group_children(groups)
    subtree = get_subtree_group_ids(group_id, children)

    result = []
    for dev in devices:
        glist = dev.get("groups", [])
        dev_gids = {g.get("id") if isinstance(g, dict) else g for g in glist}
        if dev_gids & subtree:
            result.append(dev)
    return result


def build_group_ancestry(groups: list[dict]) -> dict[str, set[str]]:
    """
    Build {group_id: {group_id + all_ancestor_ids}} map by walking parent chains.
    Mirrors reference-tool ancestry traversal so a device only needs to be in
    *any descendant* of a fuel group to be classified.
    """
    group_by_id: dict[str, dict] = {g["id"]: g for g in groups}
    ancestry: dict[str, set[str]] = {}

    def resolve(gid: str, visiting: set[str]) -> set[str]:
        if gid in ancestry:
            return ancestry[gid]
        if gid in visiting:
            return {gid}
        visiting.add(gid)

        result = {gid}
        g = group_by_id.get(gid)
        if g:
            parent = g.get("parent")
            parent_id = None
            if parent:
                parent_id = parent.get("id") if isinstance(parent, dict) else parent
                # Normalize alias (b2 → GroupCompanyId, etc.)
                parent_id = GROUP_ID_ALIASES.get(parent_id, parent_id)
            if parent_id:
                result |= resolve(parent_id, visiting)
        ancestry[gid] = result
        return result

    for g in groups:
        resolve(g["id"], set())
    return ancestry


def detect_fuel_types(devices: list[dict], groups: list[dict] | None = None) -> dict[str, dict]:
    """
    Map each device ID to its fuel type metadata by inspecting group memberships.

    When `groups` is supplied, the device's group ancestry is checked — so a vehicle
    assigned to a custom sub-group under (e.g.) GroupPluginHybridElectricVehicleId
    still resolves to PHEV. Falls back to UNKNOWN_FUEL when nothing matches.
    """
    ancestry = build_group_ancestry(groups) if groups else {}

    result: dict[str, dict] = {}
    for dev in devices:
        dev_id = dev.get("id", "")
        glist = dev.get("groups", [])
        dev_gids: set[str] = set()
        for g in glist:
            gid = g.get("id") if isinstance(g, dict) else g
            if gid:
                dev_gids.add(gid)
                # Add all ancestors of this group (if ancestry is available)
                dev_gids |= ancestry.get(gid, set())

        matched: dict | None = None
        for fuel_gid, meta in FUEL_GROUP_MAP.items():
            if fuel_gid in dev_gids:
                matched = {**meta, "group_id": fuel_gid}
                break

        result[dev_id] = matched if matched else {**UNKNOWN_FUEL}
    return result


def aggregate_fuel_type_counts(
    devices: list[dict],
    device_fuel_map: dict[str, dict],
) -> list[dict]:
    """
    Aggregate device counts by fuel type group_id.
    Returns list of {group_id, label, powertrain, vehicle_count, default_price, price_unit, idle_unit, default_idle_rate}.
    """
    counts: dict[str, dict] = {}
    for dev in devices:
        dev_id = dev.get("id", "")
        meta = device_fuel_map.get(dev_id, UNKNOWN_FUEL)
        gid = meta["group_id"]
        if gid not in counts:
            counts[gid] = {**meta, "vehicle_count": 0}
            counts[gid]["default_price"] = meta["price_per_unit"]
            counts[gid]["default_idle_rate"] = meta["idle_rate"]
        counts[gid]["vehicle_count"] += 1

    return list(counts.values())
