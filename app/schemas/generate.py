from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, field_validator


class SafetyRule(BaseModel):
    rule_id: str
    name: str = ""
    weight: float  # 0–100; all rules must sum to 100


class FuelSetting(BaseModel):
    group_id: str        # e.g. "GroupDieselId" or "unknown"
    label: str           # e.g. "Diesel"
    price_per_unit: float
    idle_rate: float     # L/h for ICE; kWh/h for EV
    price_unit: str      # "/L", "/kWh", "/kg" etc — currency prefix added separately


class GenerateRequest(BaseModel):
    group_id: str
    group_name: str
    start_date: date
    end_date: date
    language: Literal["en", "ms"] = "en"
    currency: str = "USD"
    slides: list[str]
    safety_rules: list[SafetyRule]
    fuel_settings: list[FuelSetting]

    @field_validator("safety_rules")
    @classmethod
    def weights_must_sum_to_100(cls, rules: list[SafetyRule]) -> list[SafetyRule]:
        if rules:
            total = sum(r.weight for r in rules)
            if abs(total - 100.0) > 0.5:
                raise ValueError(f"Safety rule weights must sum to 100 (got {total:.1f})")
        return rules

    @field_validator("slides")
    @classmethod
    def at_least_one_slide(cls, slides: list[str]) -> list[str]:
        if not slides:
            raise ValueError("At least one slide must be selected")
        return slides


class GenerateResponse(BaseModel):
    job_id: str
