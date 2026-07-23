"""Deterministic "Key Strategic Recommendations" generator (no AI/LLM).

Builds the closing recommendation cards for the report from the SAME analytics
DataFrames that drive the slides. There is no model call and no external
dependency — every figure quoted is computed directly from the fleet's own data
for the period, so the output is fully reproducible.

Design rules (mirrors the report's own conventions):
- One card per data signal, and a card is emitted ONLY when its signal is
  non-empty. This is the deterministic equivalent of the old ``section_empty``
  guard, so the report never invents advice for a section that had no data.
- Cards are ordered most-urgent first (at-risk → utilization → idling → safety
  → speeding → maintenance → data hygiene).
- Titles use Markdown ``**bold**`` — the report template renders ``recs[]`` with
  bold support (see report_template.html). Body text is plain prose.
- Vehicle groupings are called "groups"; monetary values are prefixed with the
  currency CODE (e.g. "MYR 1,200"), never a symbol.

See USER_GUIDE.md -> Understanding the Report -> Key Strategic Recommendations.
"""
from __future__ import annotations

import pandas as pd

from app.config import settings


def build_recommendations(
    *,
    utilization_df: pd.DataFrame,
    idling_df: pd.DataFrame,
    safety_df: pd.DataFrame,
    risk_df: pd.DataFrame,
    battery_df: pd.DataFrame,
    fault_df: pd.DataFrame,
    max_speeding_df: pd.DataFrame | None,
    device_names: dict[str, str],
    customer_map: dict[str, dict],
    device_customer_map: dict[str, str],
    currency: str = "USD",
) -> list[str]:
    """Return a prioritised list of ``"**Title:** body"`` recommendation strings.

    One card per non-empty data signal, most-urgent first. Every number mirrors
    the figures shown on the corresponding report slide, so the recommendations
    always reconcile with the charts and tables. If NO signal fires (a clean
    fleet), a single positive "Fleet Health" card is returned so the section is
    never empty.

    All DataFrame column references below are the same ones used by
    report_builder.build_slides_list, so the two stay in lock-step.
    """
    recs: list[str] = []

    # ── 1. At-Risk triage (five-factor risk matrix) ────────────────────────
    # Critical = ≥4 factors, High = exactly 3 (matches report_builder + USER_GUIDE).
    if not risk_df.empty:
        critical = int((risk_df["flag_count"] >= 4).sum())
        high = int((risk_df["flag_count"] == 3).sum())
        if critical + high > 0:
            recs.append(
                f"**At-Risk Vehicles:** {critical + high} vehicle(s) are flagged Critical "
                f"(4–5 risk factors) or High (3 factors) on the five-factor risk matrix "
                f"— {critical} Critical and {high} High. Prioritise these for immediate "
                f"review; they combine low utilization, dormancy, high idling, low safety "
                f"scores and/or high idle cost."
            )

    # ── 2. Under-utilized vehicles (below the fleet's own Q1 composite) ─────
    # Matches the utilization donut's "Under-Utilized" definition (score < Q1).
    if not utilization_df.empty:
        scores = utilization_df["composite_score"].dropna()
        if len(scores) > 1:
            q1 = scores.quantile(0.25)
            under = int((scores < q1).sum())
            if under > 0:
                recs.append(
                    f"**Under-Utilized Vehicles:** {under} vehicle(s) fall below the fleet's "
                    f"Q1 utilization score of {q1:.1f} (0–100 composite of distance, drive-hours "
                    f"and active days). Consider reallocating, right-sizing or redeploying these "
                    f"assets to lift fleet ROI."
                )

    # ── 3. Dormant vehicles (fewer active days than the threshold) ──────────
    if not utilization_df.empty and "active_days" in utilization_df.columns:
        dormant = int((utilization_df["active_days"] < settings.DORMANT_DAYS_THRESHOLD).sum())
        if dormant > 0:
            recs.append(
                f"**Dormant Vehicles:** {dormant} vehicle(s) were active on fewer than "
                f"{settings.DORMANT_DAYS_THRESHOLD} days this period. Investigate whether they are "
                f"idle spares, awaiting repair, or candidates for reassignment — each dormant unit "
                f"still carries fixed and telematics cost."
            )

    # ── 4. Idling cost (fuel-configured vehicles, matches the Idling slide) ─
    if not idling_df.empty:
        total_idle_h = float(idling_df["idle_hours"].sum())
        total_idle_cost = float(idling_df["idle_cost"].sum())
        if total_idle_cost > 0:
            top = idling_df.sort_values("idle_hours", ascending=False).iloc[0]
            top_name = device_names.get(top["device_id"], top["device_id"])
            recs.append(
                f"**Idling Cost:** The fleet idled {total_idle_h:,.0f} hours, an estimated "
                f"{currency} {total_idle_cost:,.0f} in wasted fuel/energy. The worst single vehicle "
                f"({top_name}) idled {float(top['idle_hours']):,.0f} hours. Introduce idle-time limits "
                f"and driver coaching to recover this cost."
            )

    # ── 5. High-risk drivers (safety score below the High-Risk threshold) ──
    if not safety_df.empty:
        high_risk = int((safety_df["safety_score"] < settings.SAFETY_HIGH_RISK).sum())
        if high_risk > 0:
            recs.append(
                f"**High-Risk Drivers:** {high_risk} vehicle(s) score below the "
                f"{int(settings.SAFETY_HIGH_RISK)} High-Risk safety threshold (0–100). Enrol these "
                f"drivers in targeted coaching and tackle their most frequent exception types first."
            )

    # ── 6. Speeding (top recorded speeds) ──────────────────────────────────
    if max_speeding_df is not None and not max_speeding_df.empty:
        over_120 = int((max_speeding_df["max_speed"] > 120).sum())
        top_speed = int(round(float(max_speeding_df["max_speed"].max())))
        if over_120 > 0:
            recs.append(
                f"**Speed Management:** {over_120} vehicle(s) exceeded 120 km/h, with a top recorded "
                f"speed of {top_speed} km/h. Set speed policies and in-cab alerts, and review the "
                f"highest-speed vehicles for high-risk driving behaviour."
            )

    # ── 7. Battery health (fault events) ───────────────────────────────────
    if not battery_df.empty:
        batt_events = int(battery_df["fault_count"].sum())
        if batt_events > 0:
            affected = int((battery_df["fault_count"] > 0).sum())
            recurring = int((battery_df["fault_count"] > 1).sum())
            recs.append(
                f"**Battery Health:** {batt_events} battery fault event(s) were detected across "
                f"{affected} vehicle(s), {recurring} with recurring faults (more than one event). "
                f"Schedule proactive battery checks for the recurring cases to avoid roadside failures."
            )

    # ── 8. Engine fault codes (DTC frequency) ──────────────────────────────
    if not fault_df.empty:
        total_faults = int(fault_df["count"].sum())
        if total_faults > 0:
            top_fault = fault_df.sort_values("count", ascending=False).iloc[0]
            code = top_fault.get("dtc_code", "")
            desc = (top_fault.get("description", "") or "").strip()
            top_label = f"{desc} ({code})" if desc else str(code)
            recs.append(
                f"**Engine Fault Codes:** {total_faults:,} diagnostic fault event(s) were recorded; "
                f"the most frequent code is {top_label}. Prioritise vehicles with recurring codes for "
                f"scheduled maintenance to prevent unplanned downtime."
            )

    # ── 9. Unassigned vehicles (data hygiene) ──────────────────────────────
    # Counts devices not mapped to any group — same logic as the Group Overview slide.
    if not utilization_df.empty:
        unassigned = 0
        for dev_id in utilization_df["device_id"].tolist():
            cust_id = device_customer_map.get(dev_id)
            if not (cust_id and cust_id in customer_map):
                unassigned += 1
        if unassigned > 0:
            recs.append(
                f"**Unassigned Vehicles:** {unassigned} vehicle(s) are not assigned to any group. "
                f"Assign them to the correct group so utilization, cost and risk can be tracked and "
                f"reported accurately."
            )

    # ── Fallback: a clean fleet still gets one positive card ───────────────
    # Guarantees the Recommendations section never renders "0 recommendations".
    if not recs:
        recs.append(
            "**Fleet Health:** No critical risk signals were detected this period across "
            "utilization, idling, safety, speeding or maintenance. Maintain current practices "
            "and keep monitoring the dashboard for emerging trends."
        )

    return recs
