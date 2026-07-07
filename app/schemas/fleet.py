"""Pydantic response models for the fleet-configuration API.

These models shape the JSON returned by the ``/api/...`` fleet endpoints that
populate the "Configuring a Report" screen: the group selector, the safety
exception-rule lookups, and the fuel/idling settings table. See USER_GUIDE.md
-> "Configuring a Report" (in particular "Fleet Configuration", "Safety
Scorecard Rules", and "Fuel & Idling Settings").
"""

from pydantic import BaseModel


class GroupItem(BaseModel):
    """One selectable fleet group (id, display name, and its vehicle count)."""

    id: str
    name: str
    vehicle_count: int


# UNUSED / LEGACY: GroupTreeItem backed an expandable tree-style group picker
# that was rolled back. The frontend now uses the flat /api/groups <select>
# (served via GroupListResponse / GroupItem). Retained for reference only.
class GroupTreeItem(BaseModel):
    id: str
    name: str
    parent_id: str | None
    level: int
    has_children: bool
    vehicle_count: int


class GroupListResponse(BaseModel):
    """Flat list of groups for the group dropdown on the config screen."""

    groups: list[GroupItem]


# UNUSED / LEGACY: response envelope for the rolled-back tree group picker.
# Kept alongside GroupTreeItem for reference; not consumed by the frontend.
class GroupTreeResponse(BaseModel):
    groups: list[GroupTreeItem]


class RuleItem(BaseModel):
    """A safety exception rule referenced by the user's config (resolved by id)."""

    id: str
    name: str | None
    # True when the rule id resolved to an actual rule in the MyGeotab database;
    # False means the id could not be found (name will be None / unresolved).
    found: bool


class RuleListResponse(BaseModel):
    """Resolution results for a set of requested rule ids."""

    rules: list[RuleItem]


class AvailableRuleItem(BaseModel):
    """An exception rule available in the database, offered in the rule pickers."""

    id: str
    name: str


class AvailableRulesResponse(BaseModel):
    """All exception rules available for selection in the Safety Scorecard table."""

    rules: list[AvailableRuleItem]


class FuelTypeItem(BaseModel):
    """One row of the Fuel & Idling Settings table (one detected fuel type)."""

    group_id: str
    label: str
    powertrain: str
    vehicle_count: int
    # default_price / default_idle_rate are per-powertrain baseline defaults that
    # pre-fill the editable "Price / Unit" and "Idle Rate" inputs. They originate
    # from the fuel-type default map in services/analytics/fleet.py
    # (guide -> "Default Fuel Prices & Idle Rates").
    default_price: float
    # price_unit is the denominator of the price (e.g. "/L", "/kWh", "/kg") — the
    # currency prefix is added separately from the user's selected currency.
    price_unit: str
    # idle_unit is the unit of the hourly idling consumption rate (e.g. "L/h",
    # "kWh/h", "kg/h") — i.e. how much fuel/energy is burned per idle hour.
    idle_unit: str
    default_idle_rate: float


class UnconfiguredVehicle(BaseModel):
    """A vehicle with no valid powertrain assignment (excluded from cost calc)."""

    id: str
    name: str
    serial: str | None = None


class FuelTypeListResponse(BaseModel):
    """Payload for the Fuel & Idling Settings table plus its unconfigured warning."""

    fuel_types: list[FuelTypeItem]
    total_vehicles: int
    # unconfigured_count / unconfigured_vehicles drive the warning banner for
    # vehicles with no valid powertrain assigned; these are excluded from cost
    # calculations until corrected in MyGeotab (guide -> "Fuel & Idling Settings",
    # "excluded from cost").
    unconfigured_count: int = 0
    unconfigured_vehicles: list[UnconfiguredVehicle] = []
