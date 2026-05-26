from pydantic import BaseModel


class GroupItem(BaseModel):
    id: str
    name: str
    vehicle_count: int


class GroupTreeItem(BaseModel):
    id: str
    name: str
    parent_id: str | None
    level: int
    has_children: bool
    vehicle_count: int


class GroupListResponse(BaseModel):
    groups: list[GroupItem]


class GroupTreeResponse(BaseModel):
    groups: list[GroupTreeItem]


class RuleItem(BaseModel):
    id: str
    name: str | None
    found: bool


class RuleListResponse(BaseModel):
    rules: list[RuleItem]


class AvailableRuleItem(BaseModel):
    id: str
    name: str


class AvailableRulesResponse(BaseModel):
    rules: list[AvailableRuleItem]


class FuelTypeItem(BaseModel):
    group_id: str
    label: str
    powertrain: str
    vehicle_count: int
    default_price: float
    price_unit: str
    idle_unit: str
    default_idle_rate: float


class UnconfiguredVehicle(BaseModel):
    id: str
    name: str
    serial: str | None = None


class FuelTypeListResponse(BaseModel):
    fuel_types: list[FuelTypeItem]
    total_vehicles: int
    unconfigured_count: int = 0
    unconfigured_vehicles: list[UnconfiguredVehicle] = []
