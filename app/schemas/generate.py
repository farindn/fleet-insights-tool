"""Pydantic request/response schemas for report generation (POST /api/generate).

Mirrors the configuration the SPA collects (see USER_GUIDE.md → Configuring a Report).
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, field_validator


class SafetyRule(BaseModel):
    """One exception rule in the safety scorecard, with its weighting."""
    rule_id: str
    name: str = ""
    weight: float  # 0–100; all selected rules must sum to 100


class FuelSetting(BaseModel):
    """Per-powertrain price + idle rate used to compute idling cost.

    For PHEV the UI collects TWO sides — liquid fuel (``price_per_unit`` /
    ``idle_rate``) and electricity (``price_per_unit_elec`` / ``idle_rate_elec``)
    — and idling cost sums both (see analytics/idling.py and USER_GUIDE.md →
    Fuel & Idling Settings). The ``*_elec`` fields are None for single-fuel
    powertrains.
    """
    group_id: str        # e.g. "GroupDieselId" or "unknown"
    label: str           # e.g. "Diesel"
    price_per_unit: float
    idle_rate: float     # L/h for ICE; kWh/h for EV
    price_unit: str      # "/L", "/kWh", "/kg" etc — currency prefix added separately
    # PHEV only: electricity side (the fields above are then the liquid-fuel side).
    price_per_unit_elec: float | None = None  # per kWh
    idle_rate_elec: float | None = None       # kWh/h


class GenerateRequest(BaseModel):
    """Full report-generation request posted by the SPA."""
    group_id: str
    group_name: str
    start_date: date
    end_date: date
    currency: str = "USD"          # display currency code, prefixed to money values
    slides: list[str]             # selected report-section keys (≥1 required)
    safety_rules: list[SafetyRule]
    fuel_settings: list[FuelSetting]

    @field_validator("safety_rules")
    @classmethod
    def weights_must_sum_to_100(cls, rules: list[SafetyRule]) -> list[SafetyRule]:
        """Safety rule weights must total 100% (±0.5 for rounding).

        An empty list is allowed — that is the case when the Safety & Risk
        section is not selected, so the scorecard does not apply.
        """
        if rules:  # only enforced when Safety & Risk rules were provided
            total = sum(r.weight for r in rules)
            if abs(total - 100.0) > 0.5:  # 0.5 tolerance matches the UI weight bar
                raise ValueError(f"Safety rule weights must sum to 100 (got {total:.1f})")
        return rules

    @field_validator("slides")
    @classmethod
    def at_least_one_slide(cls, slides: list[str]) -> list[str]:
        """At least one report section must be selected."""
        if not slides:
            raise ValueError("At least one slide must be selected")
        return slides


class GenerateResponse(BaseModel):
    """Response to POST /api/generate — the async job identifier."""
    job_id: str
