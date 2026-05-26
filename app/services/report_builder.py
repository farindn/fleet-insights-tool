"""Report builder: assemble SLIDES JSON and inject into HTML template."""
from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from app.config import settings
from app.services.analytics.faults import dtc_code

_TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "report_template.html"

RISK_COLORS = {
    "Critical": "#C62828",
    "Warning": "#EF6C00",
    "Monitor": "#F9A825",
    "OK": "#2E7D32",
}

SAFETY_BAR_COLORS = [
    "#C62828", "#6A1B9A", "#1565C0", "#E65100", "#F9A825", "#2E7D32",
]

DONUT_SAFETY = [
    {"label": "High Risk",   "color": "#C62828"},
    {"label": "Medium Risk", "color": "#EF6C00"},
    {"label": "Mild Risk",   "color": "#F9A825"},
    {"label": "Low Risk",    "color": "#2E7D32"},
]


def _fmt(val: float | int, decimals: int = 0) -> str:
    """Format number with commas."""
    if math.isnan(float(val)):
        return "—"
    if decimals == 0:
        return f"{int(round(val)):,}"
    return f"{val:,.{decimals}f}"


def _months_label(start: date, end: date) -> str:
    """Human-readable month count like '6 months'."""
    months = (end.year - start.year) * 12 + (end.month - start.month) + 1
    return f"{months} month{'s' if months != 1 else ''}"


def _period_str(start: date, end: date) -> str:
    return f"{start} → {end}"


def _run_ts() -> str:
    from zoneinfo import ZoneInfo
    try:
        now = datetime.now(ZoneInfo("Asia/Kuala_Lumpur"))
    except Exception:
        now = datetime.utcnow()
    return f"{now.day} {now.strftime('%b %Y, %H:%M')} MYT"


def _q1_q3(series: pd.Series):
    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    return q1, q3


def _utilization_tier(score: float, q1: float, q3: float) -> tuple[str, str, str]:
    """Returns (label, flag, row_bg)."""
    if score > q3:
        return "Over", "orange", "rgba(255,167,38,0.10)"
    if score >= q1:
        return "Optimum", "green", ""
    return "Under", "red", "rgba(239,83,80,0.10)"


def build_slides_list(
    *,
    db: str,
    db_display: str,
    group_name: str,
    currency: str = "USD",
    start_date: date,
    end_date: date,
    slides: list[str],
    utilization_df: pd.DataFrame,
    monthly_df: pd.DataFrame,
    idling_df: pd.DataFrame,
    safety_df: pd.DataFrame,
    rule_names: dict[str, str],
    safety_rules: list[dict],
    exception_events: dict[str, list[dict]],
    battery_df: pd.DataFrame,
    fault_df: pd.DataFrame,
    risk_df: pd.DataFrame,
    gps_points: list[list[float]],
    customer_map: dict[str, dict],
    device_customer_map: dict[str, str],
    device_names: dict[str, str],
    ai_insights: dict[str, str],
    recommendations: list[str],
    battery_fault_data: list[dict] | None = None,
    engine_fault_data: list[dict] | None = None,
    max_speeding_df: pd.DataFrame | None = None,
) -> list[dict]:
    period = _period_str(start_date, end_date)
    months_label = _months_label(start_date, end_date)
    month_count = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month) + 1
    slide_set = set(slides)
    result: list[dict] = []

    # ── 1. Cover ───────────────────────────────────────────────────────────────
    result.append({
        "type": "cover",
        "line1": "Analytics Report",
        "line2": "Fleet Data Insights",
        "line3": "Powered by Geotab",
        "db": db,
        "period": period,
        "run_ts": _run_ts(),
        "db_display": db_display,
    })

    # ── 2. Portfolio ───────────────────────────────────────────────────────────
    if "portfolio" in slide_set:
        total_vehicles = len(utilization_df)
        cust_counts: dict[str, int] = {}
        unassigned = 0
        for dev_id in (utilization_df["device_id"].tolist() if not utilization_df.empty else []):
            cust_id = device_customer_map.get(dev_id)
            if cust_id and cust_id in customer_map:
                name = customer_map[cust_id]["name"].upper()
                cust_counts[name] = cust_counts.get(name, 0) + 1
            else:
                unassigned += 1

        rows = sorted(cust_counts.items(), key=lambda x: -x[1])
        port_rows = [{"name": n, "count": c, "pct": round(c / max(total_vehicles, 1) * 100, 1), "unassigned": False}
                     for n, c in rows]
        if unassigned:
            port_rows.append({"name": "UNASSIGNED", "count": unassigned,
                               "pct": round(unassigned / max(total_vehicles, 1) * 100, 1), "unassigned": True})
        port_rows.sort(key=lambda x: -x["count"])

        insight = ai_insights.get("portfolio", (
            f"Fleet spans {len(cust_counts)} active groups with {total_vehicles} vehicles "
            f"under telematics monitoring. {unassigned} vehicle(s) are currently unassigned to any group."
        ))

        result.append({
            "type": "portfolio",
            "title": "Group Overview",
            "icon": "demography",
            "insight": insight,
            "rows": port_rows,
            "metrics": [
                {"label": "Groups", "value": str(len(cust_counts))},
                {"label": "Total Vehicles", "value": str(total_vehicles)},
            ],
        })

    # ── 3. Heatmap ────────────────────────────────────────────────────────────
    if "heatmap" in slide_set:
        result.append({
            "type": "heatmap",
            "title": "Geographic Coverage",
            "icon": "map_search",
            "gps_points": gps_points,
            "metrics": [
                {"label": "GPS Stop-Points", "value": _fmt(len(gps_points))},
                {"label": "Analysis Period", "value": months_label},
            ],
        })

    # ── 4–9. Utilization ──────────────────────────────────────────────────────
    if "utilization" in slide_set and not utilization_df.empty:
        udf = utilization_df.copy()
        scores = udf["composite_score"].dropna()
        q1_score, q3_score = (scores.quantile(0.25), scores.quantile(0.75)) if len(scores) > 1 else (0, 100)

        # Days driven table
        days_df = udf.sort_values("active_days", ascending=False)
        q1_days, q3_days = _q1_q3(udf["active_days"])
        day_rows = []
        for _, r in days_df.iterrows():
            dev_id = r["device_id"]
            d = int(r["active_days"])
            status = "Optimum" if d >= q1_days else "Under"
            flag = "green" if status == "Optimum" else "red"
            bg = "" if status == "Optimum" else "rgba(239,83,80,0.10)"
            cust_name = customer_map.get(device_customer_map.get(dev_id, ""), {}).get("name", "UNASSIGNED").upper()
            day_rows.append({"cells": [device_names.get(dev_id, dev_id), cust_name, str(d), status],
                             "flag": flag, "row_bg": bg})
        result.append({
            "type": "table", "title": f"Days Driven (Last {months_label})",
            "icon": "calendar_month",
            "insight": ai_insights.get("days_driven",
                f"Total driving days per vehicle over the {months_label}. Vehicles below the Q1 threshold of "
                f"{int(q1_days)} days are highlighted as under-deployed."),
            "cols": ["Vehicle", "Group", "Days Driven", "Status"],
            "rows": day_rows,
            "metrics": [{"label": "Q1 Threshold", "value": f"{int(q1_days)} days"},
                        {"label": "Q3 Threshold", "value": f"{int(q3_days)} days"},
                        {"label": "Fleet Size", "value": str(len(udf))}],
        })

        # Distance table
        dist_df = udf.sort_values("total_distance_km", ascending=False)
        q1_dist, q3_dist = _q1_q3(udf["total_distance_km"])
        dist_rows = []
        for _, r in dist_df.iterrows():
            dev_id = r["device_id"]
            d = r["total_distance_km"]
            if d > q3_dist:
                status, flag, bg = "Over", "orange", "rgba(255,167,38,0.10)"
            elif d >= q1_dist:
                status, flag, bg = "Optimum", "green", ""
            else:
                status, flag, bg = "Under", "red", "rgba(239,83,80,0.10)"
            cust = customer_map.get(device_customer_map.get(dev_id, ""), {}).get("name", "UNASSIGNED").upper()
            dist_rows.append({"cells": [device_names.get(dev_id, dev_id), cust, _fmt(d), status],
                              "flag": flag, "row_bg": bg})
        result.append({
            "type": "table", "title": f"Distance Travelled (Last {months_label})",
            "icon": "route",
            "insight": ai_insights.get("distance",
                f"Total distance per vehicle over the full {months_label}. "
                f"Red = below Q1 ({_fmt(q1_dist)} km); orange = above Q3 ({_fmt(q3_dist)} km)."),
            "cols": ["Vehicle", "Group", "Distance (km)", "Status"],
            "rows": dist_rows,
            "metrics": [{"label": "Q1 Threshold", "value": f"{_fmt(q1_dist)} km"},
                        {"label": "Q3 Threshold", "value": f"{_fmt(q3_dist)} km"},
                        {"label": "Fleet Size", "value": str(len(udf))}],
        })

        # Drive hours table
        hr_df = udf.sort_values("total_drive_hours", ascending=False)
        q1_hr, q3_hr = _q1_q3(udf["total_drive_hours"])
        hr_rows = []
        for _, r in hr_df.iterrows():
            dev_id = r["device_id"]
            h = r["total_drive_hours"]
            if h > q3_hr:
                status, flag, bg = "Over", "orange", "rgba(255,167,38,0.10)"
            elif h >= q1_hr:
                status, flag, bg = "Optimum", "green", ""
            else:
                status, flag, bg = "Under", "red", "rgba(239,83,80,0.10)"
            cust = customer_map.get(device_customer_map.get(dev_id, ""), {}).get("name", "UNASSIGNED").upper()
            hr_rows.append({"cells": [device_names.get(dev_id, dev_id), cust, f"{h:.1f}", status],
                            "flag": flag, "row_bg": bg})
        result.append({
            "type": "table", "title": f"Driving Duration (Last {months_label})",
            "icon": "timer",
            "insight": ai_insights.get("drive_hours",
                f"Total engine-on driving hours per vehicle over the {months_label}. "
                f"Red = below Q1 ({q1_hr:.1f} h); orange = above Q3 ({q3_hr:.1f} h)."),
            "cols": ["Vehicle", "Group", "Drive Time (h)", "Status"],
            "rows": hr_rows,
            "metrics": [{"label": "Q1 Threshold", "value": f"{q1_hr:.1f} h"},
                        {"label": "Q3 Threshold", "value": f"{q3_hr:.1f} h"},
                        {"label": "Fleet Size", "value": str(len(udf))}],
        })

        # Monthly utilization trend (line-only)
        if not monthly_df.empty:
            monthly_scores = []
            for month_str in sorted(monthly_df["month"].unique()):
                m_df = monthly_df[monthly_df["month"] == month_str]
                total_dist = m_df["distance_km"].sum()
                total_hrs = m_df["drive_hours"].sum()
                # Simple composite: normalize against Q3 thresholds
                dist_score = min(100, total_dist / max(q3_dist * len(udf), 1) * 100)
                hrs_score = min(100, total_hrs / max(q3_hr * len(udf), 1) * 100)
                avg_score = round(0.6 * dist_score + 0.4 * hrs_score, 1)
                try:
                    dt = datetime.strptime(month_str, "%Y-%m")
                    label = dt.strftime("%b %Y")
                except Exception:
                    label = month_str
                monthly_scores.append({"month": label, "avg_score": avg_score})

            result.append({
                "type": "line-only",
                "title": f"Fleet Utilization (Last {months_label})",
                "icon": "show_chart",
                "insight": ai_insights.get("utilization_trend",
                    f"Monthly fleet utilization score (0–100) combining normalized distance and driving duration. "
                    f"Q1={q1_score:.1f}  Q3={q3_score:.1f}."),
                "line_data": monthly_scores,
                "line_key": "avg_score",
                "line_label": "Fleet Avg Utilization Score (0–100)",
                "line_color": "#1565C0",
                "metrics": [{"label": "Q1 Score", "value": f"{q1_score:.1f}"},
                            {"label": "Q3 Score", "value": f"{q3_score:.1f}"},
                            {"label": "Months", "value": str(month_count)}],
            })

        # Utilization donut
        under = int((scores < q1_score).sum())
        over = int((scores > q3_score).sum())
        optimum = len(udf) - under - over
        result.append({
            "type": "donut",
            "title": "Fleet Utilization Distribution",
            "icon": "donut_large",
            "insight": ai_insights.get("utilization_donut",
                f"{optimum} vehicles ({round(optimum/max(len(udf),1)*100)}%) are within the optimum utilization band. "
                f"{under} are under-utilized and {over} are over-utilized based on composite score "
                f"(Q1={q1_score:.1f}–Q3={q3_score:.1f})."),
            "donut": [
                {"label": "Under-Utilized", "count": under, "color": "#EF5350"},
                {"label": "Optimum", "count": optimum, "color": "#43A047"},
                {"label": "Over-Utilized", "count": over, "color": "#FFA726"},
            ],
            "total": len(udf),
            "donut_sub": f"Q1={q1_score:.1f}  Q3={q3_score:.1f}",
            "legend_right": True,
            "metrics": [{"label": "Under-Utilized", "value": str(under)},
                        {"label": "Optimum", "value": str(optimum)},
                        {"label": "Over-Utilized", "value": str(over)}],
        })

        # Utilization by vehicle table
        util_rows = []
        for _, r in udf.sort_values("composite_score", ascending=False).iterrows():
            dev_id = r["device_id"]
            score = r["composite_score"]
            status, flag, bg = _utilization_tier(score, q1_score, q3_score)
            cust = customer_map.get(device_customer_map.get(dev_id, ""), {}).get("name", "UNASSIGNED").upper()
            util_rows.append({
                "cells": [device_names.get(dev_id, dev_id), cust,
                          str(int(r["active_days"])), _fmt(r["total_distance_km"]),
                          f"{r['total_drive_hours']:.1f}", f"{score:.1f}", status],
                "flag": flag, "row_bg": bg,
            })
        result.append({
            "type": "table",
            "title": "Fleet Utilization by Vehicle",
            "icon": "directions_car",
            "insight": ai_insights.get("utilization_table",
                f"Composite score (0–100) per vehicle combining days driven, distance, and driving duration. "
                f"Red = under-utilized (below Q1={q1_score:.1f}); orange = over-utilized (above Q3={q3_score:.1f})."),
            "cols": ["Vehicle", "Group", "Days", "Distance (km)", "Drive (h)", "Score", "Status"],
            "rows": util_rows,
            "metrics": [{"label": "Under-Utilized", "value": str(under)},
                        {"label": "Optimum", "value": str(optimum)},
                        {"label": "Over-Utilized", "value": str(over)}],
        })

    # ── 10–11. Idling ─────────────────────────────────────────────────────────
    # Use idle_hours and cost from idling_df (fuel-configured vehicles only for consistency)
    if "idling" in slide_set:
        # Total idle hours and cost from idling_df (fuel-configured vehicles only)
        total_idle_h = idling_df["idle_hours"].sum() if not idling_df.empty else 0
        total_idle_cost = idling_df["idle_cost"].sum() if not idling_df.empty else 0

        # Calculate average cost rate from fuel-configured vehicles
        avg_rate = total_idle_cost / max(total_idle_h, 1) if total_idle_h > 0 else 0

        # Monthly idling - only count fuel-configured devices for consistency
        idle_monthly: list[dict] = []
        if not monthly_df.empty and not idling_df.empty:
            # Filter monthly_df to only include fuel-configured devices
            fuel_device_ids = set(idling_df["device_id"].unique())
            monthly_fuel_df = monthly_df[monthly_df["device_id"].isin(fuel_device_ids)]

            for month_str in sorted(monthly_fuel_df["month"].unique()):
                m_df = monthly_fuel_df[monthly_fuel_df["month"] == month_str]
                ih = m_df["idle_hours"].sum()
                ic = round(ih * avg_rate)
                try:
                    dt = datetime.strptime(month_str, "%Y-%m")
                    label = dt.strftime("%b %Y")
                except Exception:
                    label = month_str
                idle_monthly.append({"month": label, "idle_hours": round(ih, 1),
                                     "idle_cost_rm": ic})
            # Normalize bar/line pct
            max_ih = max((x["idle_hours"] for x in idle_monthly), default=1)
            for x in idle_monthly:
                x["bar_pct"] = round(x["idle_hours"] / max_ih * 100, 1)
                x["line_pct"] = x["bar_pct"]

        # Summarise burn rate for display
        sample_row = idling_df.iloc[0] if not idling_df.empty else {}
        burn_rate = sample_row.get("idle_rate", 2.5) if hasattr(sample_row, "get") else 2.5
        price = sample_row.get("price_per_unit", 2.15) if hasattr(sample_row, "get") else 2.15

        result.append({
            "type": "bar-line",
            "title": f"Idling Duration (Last {months_label})",
            "icon": "local_gas_station",
            "insight": ai_insights.get("idling",
                f"The fleet accumulated {_fmt(total_idle_h, 0)} idle hours over the period, generating an estimated "
                f"{currency} {_fmt(total_idle_cost)} in wasted fuel cost at {currency} {price:.2f}/unit and {burn_rate} idle burn rate."),
            "data": idle_monthly,
            "metrics": [{"label": "Total Idle Hours", "value": f"{_fmt(total_idle_h)}h"},
                        {"label": "Est. Fuel Waste", "value": f"{currency} {_fmt(total_idle_cost)}"},
                        {"label": "Burn Rate", "value": f"{burn_rate} L/h"}],
        })

        # Top 15 idlers hbar - use utilization_df for hours (all vehicles)
        if not utilization_df.empty and "total_idle_hours" in utilization_df.columns:
            # Merge idle cost from idling_df for display
            top15_df = utilization_df[utilization_df["total_idle_hours"] > 0].nlargest(15, "total_idle_hours").copy()
            # Add idle_cost from idling_df if available
            if not idling_df.empty:
                cost_map = idling_df.set_index("device_id")["idle_cost"].to_dict()
                top15_df["idle_cost"] = top15_df["device_id"].map(cost_map).fillna(0)
            else:
                top15_df["idle_cost"] = 0

            max_h = top15_df["total_idle_hours"].max() if not top15_df.empty else 1
            hbar_rows = []
            for _, r in top15_df.iterrows():
                dev_id = r["device_id"]
                cust = customer_map.get(device_customer_map.get(dev_id, ""), {}).get("name", "").upper()
                ih = r["total_idle_hours"]
                ic = r["idle_cost"]
                hbar_rows.append({
                    "label": device_names.get(dev_id, dev_id),
                    "sub": cust,
                    "value": round(ih, 1),
                    "value2": f"{currency} {_fmt(ic)}" if ic > 0 else "—",
                    "pct": round(ih / max_h * 100, 1),
                })
        else:
            hbar_rows = []

        result.append({
            "type": "hbar",
            "title": f"Idling Duration — Top 15 Vehicles",
            "icon": "hourglass",
            "insight": ai_insights.get("idling_top15",
                "The 15 highest-idling vehicles account for a disproportionate share of estimated fuel waste. "
                "Targeted driver coaching and idle-reduction policies for these vehicles can yield the fastest reduction."),
            "bars": hbar_rows,
            "value2_label": "Est. Cost",
            "bar_color": "#1565C0",
            "metrics": [{"label": "Fleet Total Idle", "value": f"{_fmt(total_idle_h)}h"},
                        {"label": "Est. Total Cost", "value": f"{currency} {_fmt(total_idle_cost)}"}],
        })

    # ── 12–14. Safety ─────────────────────────────────────────────────────────
    if "safety" in slide_set and not safety_df.empty:
        scores_s = safety_df["safety_score"].dropna()
        high_risk = int((scores_s < settings.SAFETY_HIGH_RISK).sum())
        med_risk = int(((scores_s >= settings.SAFETY_HIGH_RISK) & (scores_s < settings.SAFETY_MEDIUM_RISK)).sum())
        mild_risk = int(((scores_s >= settings.SAFETY_MEDIUM_RISK) & (scores_s < 90)).sum())
        low_risk = int((scores_s >= 90).sum())

        result.append({
            "type": "donut",
            "title": f"Safety & Risk (Last {months_label})",
            "icon": "health_and_safety",
            "insight": ai_insights.get("safety_donut",
                f"{high_risk} vehicles ({round(high_risk/max(len(safety_df),1)*100)}% of the fleet) are classified as "
                f"High Risk. A further {med_risk} are Medium Risk — combined, {high_risk+med_risk} vehicles require "
                "active coaching and account manager follow-up."),
            "donut": [
                {"label": "High Risk",   "count": high_risk,   "color": "#C62828"},
                {"label": "Medium Risk", "count": med_risk,    "color": "#EF6C00"},
                {"label": "Mild Risk",   "count": mild_risk,   "color": "#F9A825"},
                {"label": "Low Risk",    "count": low_risk,    "color": "#2E7D32"},
            ],
            "total": len(safety_df),
            "donut_sub": f"{months_label}",
            "legend_right": True,
            "metrics": [
                {"label": "High Risk",   "value": str(high_risk),   "sub": f"score ≤ {int(settings.SAFETY_HIGH_RISK)}"},
                {"label": "Medium Risk", "value": str(med_risk),    "sub": f"{int(settings.SAFETY_HIGH_RISK)}–{int(settings.SAFETY_MEDIUM_RISK)}"},
                {"label": "Mild Risk",   "value": str(mild_risk),   "sub": f"{int(settings.SAFETY_MEDIUM_RISK)}–90"},
                {"label": "Low Risk",    "value": str(low_risk),    "sub": "score ≥ 90"},
            ],
        })

        # Safety events vbar
        rule_events = []
        total_events = 0
        for i, rule in enumerate(safety_rules):
            rid = rule["rule_id"]
            events = exception_events.get(rid, [])
            cnt = len(events)
            total_events += cnt
            rule_events.append((rule_names.get(rid, rid), cnt, SAFETY_BAR_COLORS[i % len(SAFETY_BAR_COLORS)]))
        rule_events.sort(key=lambda x: -x[1])
        top_name = rule_events[0][0] if rule_events else "N/A"

        result.append({
            "type": "vbar",
            "title": f"Safety & Risk — Events",
            "icon": "emergency_home",
            "insight": ai_insights.get("safety_events",
                f"{top_name} is the most frequent safety violation with {_fmt(rule_events[0][1] if rule_events else 0)} events "
                f"({round(rule_events[0][1]/max(total_events,1)*100) if rule_events else 0}% of all "
                f"{_fmt(total_events)} recorded events fleet-wide)."),
            "bars": [{"label": n, "value": c, "color": color} for n, c, color in rule_events],
            "metrics": [{"label": "Total Events", "value": _fmt(total_events)},
                        {"label": "Rule Types", "value": str(len(safety_rules))}],
        })

        # Max Speeding Top 15 vbar
        if max_speeding_df is not None and not max_speeding_df.empty:
            speeding_bars = []
            for _, r in max_speeding_df.iterrows():
                speed_val = int(round(r["max_speed"]))
                speeding_bars.append({
                    "label": r["device_name"],
                    "value": speed_val,
                    "color": "#EF5350" if speed_val > 120 else "#EF6C00" if speed_val > 100 else "#1565C0",
                })
            max_speed_overall = int(round(max_speeding_df["max_speed"].max())) if not max_speeding_df.empty else 0
            avg_max_speed = int(round(max_speeding_df["max_speed"].mean())) if not max_speeding_df.empty else 0
            over_120 = int((max_speeding_df["max_speed"] > 120).sum())
            result.append({
                "type": "vbar",
                "title": "Safety & Risk — Max Speeding",
                "icon": "speed",
                "insight": ai_insights.get("max_speeding",
                    f"The top 15 vehicles by maximum recorded speed are shown below. "
                    f"The highest speed recorded was {max_speed_overall} km/h. "
                    f"{over_120} vehicle(s) exceeded 120 km/h, indicating potential high-risk driving behavior."),
                "bars": speeding_bars,
                "metrics": [{"label": "Max Speed", "value": f"{max_speed_overall} km/h"},
                            {"label": "Avg Max Speed (Top 15)", "value": f"{avg_max_speed} km/h"},
                            {"label": "Over 120 km/h", "value": str(over_120)}],
            })

        # Bottom 15 safety hbar-threshold
        bottom15 = safety_df.nsmallest(15, "safety_score")
        safety_bars = []
        for _, r in bottom15.iterrows():
            dev_id = r["device_id"]
            score = r["safety_score"] if not math.isnan(r["safety_score"]) else 100
            if score < settings.SAFETY_HIGH_RISK:
                cls = "High Risk"
            elif score < settings.SAFETY_MEDIUM_RISK:
                cls = "Medium Risk"
            elif score < 90:
                cls = "Mild Risk"
            else:
                cls = "Low Risk"
            cust = customer_map.get(device_customer_map.get(dev_id, ""), {}).get("name", "UNASSIGNED").upper()
            safety_bars.append({
                "label": device_names.get(dev_id, dev_id),
                "sub": cust,
                "value": round(score, 1),
                "pct": round(score, 1),
                "cls": cls,
            })
        avg_bottom = round(sum(b["value"] for b in safety_bars) / max(len(safety_bars), 1), 1)
        result.append({
            "type": "hbar-threshold",
            "title": "Safety & Risk — Bottom 15 Vehicles",
            "icon": "e911_emergency",
            "insight": ai_insights.get("safety_bottom15",
                f"The 15 lowest-scoring vehicles are listed below. Each bar represents a composite safety score (0–100). "
                f"Vehicles scoring below {int(settings.SAFETY_HIGH_RISK)} are High Risk and require immediate targeted coaching."),
            "bars": safety_bars,
            "thr1": settings.SAFETY_HIGH_RISK,
            "thr2": settings.SAFETY_MEDIUM_RISK,
            "thr3": 90,
            "metrics": [{"label": "Avg Score (Bottom 15)", "value": str(avg_bottom)},
                        {"label": "Need Coaching", "value": str(high_risk + med_risk), "sub": "High + Medium Risk"},
                        {"label": "Top Violation", "value": top_name if rule_events else "N/A"}],
        })

    # ── 15–16. Battery ────────────────────────────────────────────────────────
    if "battery" in slide_set:
        # Build per-device fault names from battery_fault_data
        # Only include codes 131, 135, 290 (battery health codes)
        BATTERY_FAULT_CODES = {131, 135, 290}
        device_fault_names: dict[str, set[str]] = {}
        if battery_fault_data:
            for fd in battery_fault_data:
                dev = fd.get("device", {})
                dev_id = dev.get("id") if isinstance(dev, dict) else dev
                diag = fd.get("diagnostic", {})
                code = diag.get("code") if isinstance(diag, dict) else None
                name = diag.get("name") if isinstance(diag, dict) else None
                if code is not None:
                    try:
                        code_int = int(code)
                    except (ValueError, TypeError):
                        continue
                    if code_int in BATTERY_FAULT_CODES and name:
                        if dev_id not in device_fault_names:
                            device_fault_names[dev_id] = set()
                        device_fault_names[dev_id].add(f"{name} ({code_int})")

        # Use fault_data to find battery faults (passed in via battery_df)
        # battery_df has device_id, fault_count columns
        if not battery_df.empty:
            total_batt_events = int(battery_df["fault_count"].sum())
            affected = int((battery_df["fault_count"] > 0).sum())
            recurring = int((battery_df["fault_count"] > 1).sum())
        else:
            total_batt_events = affected = recurring = 0

        batt_rows = []
        if not battery_df.empty:
            for _, r in battery_df[battery_df["fault_count"] > 0].sort_values("fault_count", ascending=False).iterrows():
                dev_id = r["device_id"]
                cnt = int(r["fault_count"])
                flag = "red" if cnt > 1 else "orange"
                cust = customer_map.get(device_customer_map.get(dev_id, ""), {}).get("name", "UNASSIGNED").upper()
                # Get actual fault names for this device
                fault_names = device_fault_names.get(dev_id, set())
                fault_str = "\n".join(sorted(fault_names)) if fault_names else "Battery fault detected"
                batt_rows.append({
                    "cells": [device_names.get(dev_id, dev_id), cust, str(cnt), fault_str],
                    "flag": flag,
                })

        result.append({
            "type": "table",
            "title": f"Battery Health (Last {months_label})",
            "icon": "battery_error",
            "insight": ai_insights.get("battery",
                f"{total_batt_events} battery fault events detected across {affected} vehicles. "
                f"{recurring} vehicles show recurring battery faults (more than 1 event) and should be prioritised."),
            "cols": ["Vehicle", "Group", "Events", "Fault Names"],
            "rows": batt_rows,
            "metrics": [{"label": "Total Events", "value": str(total_batt_events)},
                        {"label": "Vehicles Affected", "value": str(affected)},
                        {"label": "Recurring (>1)", "value": str(recurring)}],
        })

        # Battery by customer
        cust_batt: dict[str, dict] = {}
        for _, r in battery_df.iterrows():
            if r["fault_count"] <= 0:
                continue
            dev_id = r["device_id"]
            cust_id = device_customer_map.get(dev_id, "")
            cname = customer_map.get(cust_id, {}).get("name", "UNASSIGNED").upper()
            if cname not in cust_batt:
                cust_batt[cname] = {"events": 0, "vehicles": set()}
            cust_batt[cname]["events"] += int(r["fault_count"])
            cust_batt[cname]["vehicles"].add(dev_id)
        cust_batt_rows = []
        for cname, data in sorted(cust_batt.items(), key=lambda x: -x[1]["events"]):
            flag = "red" if data["events"] > 2 else "orange"
            cust_batt_rows.append({"cells": [cname, str(data["events"]), str(len(data["vehicles"]))], "flag": flag})

        result.append({
            "type": "table",
            "title": "Battery Health — Affected Groups",
            "icon": "battery_error",
            "insight": ai_insights.get("battery_customers",
                f"{len(cust_batt)} groups have vehicles with battery fault events. "
                "Coordinate directly with affected accounts to schedule maintenance."),
            "cols": ["Group", "Total Events", "Vehicles Affected"],
            "rows": cust_batt_rows,
            "metrics": [{"label": "Affected Groups", "value": str(len(cust_batt))},
                        {"label": "Total Events", "value": str(total_batt_events)}],
        })

    # ── 17. Fault codes ───────────────────────────────────────────────────────
    if "faults" in slide_set:
        total_faults = int(fault_df["count"].sum()) if not fault_df.empty else 0

        # Build per-vehicle fault data from engine_fault_data
        device_fault_counts: dict[str, int] = {}
        device_fault_names: dict[str, set[str]] = {}
        if engine_fault_data:
            for fd in engine_fault_data:
                dev = fd.get("device", {})
                dev_id = dev.get("id") if isinstance(dev, dict) else dev
                if not dev_id:
                    continue
                device_fault_counts[dev_id] = device_fault_counts.get(dev_id, 0) + 1
                diag = fd.get("diagnostic", {})
                name = diag.get("name") if isinstance(diag, dict) else None
                code = dtc_code(fd)  # Convert to proper DTC format (e.g., P0405)
                if name:
                    if dev_id not in device_fault_names:
                        device_fault_names[dev_id] = set()
                    label = f"{name} ({code})" if code else name
                    device_fault_names[dev_id].add(label)

        affected_vehicles = len(device_fault_counts)

        # Build label "Name (Code)" using descriptions from fault_df
        fault_bars = []
        if not fault_df.empty:
            max_cnt = fault_df["count"].max()
            for _, r in fault_df.iterrows():
                code = r["dtc_code"]
                desc = r.get("description", "") or ""
                label = f"{desc} ({code})" if desc else code
                fault_bars.append({
                    "label": label,
                    "value": int(r["count"]),
                    "pct": round(int(r["count"]) / max(max_cnt, 1) * 100, 1),
                })
        if not fault_bars:
            fault_bars = [{"label": "No fault data available", "value": 0, "pct": 0}]

        result.append({
            "type": "hbar",
            "title": f"Fault Codes (Last {months_label})",
            "icon": "car_gear",
            "insight": ai_insights.get("faults",
                f"{_fmt(total_faults)} diagnostic fault events recorded across {affected_vehicles} vehicles. "
                "The chart shows the top DTC codes by frequency — recurring codes indicate maintenance patterns."),
            "bars": fault_bars,
            "bar_color": "#C62828",
            "metrics": [{"label": "Total Fault Events", "value": _fmt(total_faults)},
                        {"label": "Vehicles Affected", "value": str(affected_vehicles)}],
        })

        # Per-vehicle fault detail table
        recurring_faults = sum(1 for c in device_fault_counts.values() if c > 1)
        fault_vehicle_rows = []
        for dev_id, cnt in sorted(device_fault_counts.items(), key=lambda x: -x[1]):
            flag = "red" if cnt > 1 else "orange"
            cust = customer_map.get(device_customer_map.get(dev_id, ""), {}).get("name", "UNASSIGNED").upper()
            fault_names = device_fault_names.get(dev_id, set())
            fault_str = "\n".join(sorted(fault_names)) if fault_names else "—"
            fault_vehicle_rows.append({
                "cells": [device_names.get(dev_id, dev_id), cust, str(cnt), fault_str],
                "flag": flag,
            })

        result.append({
            "type": "table",
            "title": f"Fault Codes (Last {months_label})",
            "icon": "car_gear",
            "insight": ai_insights.get("faults_vehicles",
                f"{_fmt(total_faults)} fault events detected across {affected_vehicles} vehicles. "
                f"{recurring_faults} vehicles show recurring faults (more than 1 event) and should be prioritised."),
            "cols": ["Vehicle", "Group", "Events", "Fault Names"],
            "rows": fault_vehicle_rows,
            "metrics": [{"label": "Total Events", "value": _fmt(total_faults)},
                        {"label": "Vehicles Affected", "value": str(affected_vehicles)},
                        {"label": "Recurring (>1)", "value": str(recurring_faults)}],
        })

        # Fault codes by group
        cust_faults: dict[str, dict] = {}
        for dev_id, cnt in device_fault_counts.items():
            cust_id = device_customer_map.get(dev_id, "")
            cname = customer_map.get(cust_id, {}).get("name", "UNASSIGNED").upper()
            if cname not in cust_faults:
                cust_faults[cname] = {"events": 0, "vehicles": set()}
            cust_faults[cname]["events"] += cnt
            cust_faults[cname]["vehicles"].add(dev_id)

        cust_fault_rows = []
        for cname, data in sorted(cust_faults.items(), key=lambda x: -x[1]["events"]):
            flag = "red" if data["events"] > 2 else "orange"
            cust_fault_rows.append({
                "cells": [cname, str(data["events"]), str(len(data["vehicles"]))],
                "flag": flag,
            })

        result.append({
            "type": "table",
            "title": "Fault Codes — Affected Groups",
            "icon": "car_gear",
            "insight": ai_insights.get("faults_customers",
                f"{len(cust_faults)} groups have vehicles with fault code events. "
                "Coordinate directly with affected accounts to schedule maintenance."),
            "cols": ["Group", "Total Events", "Vehicles Affected"],
            "rows": cust_fault_rows,
            "metrics": [{"label": "Affected Groups", "value": str(len(cust_faults))},
                        {"label": "Total Events", "value": _fmt(total_faults)}],
        })

    # ── 18–19. At-risk ────────────────────────────────────────────────────────
    if "risk" in slide_set and not risk_df.empty:
        critical = int((risk_df["flag_count"] >= 3).sum())
        high = int((risk_df["flag_count"] == 3).sum())
        medium = int(((risk_df["flag_count"] >= 1) & (risk_df["flag_count"] < 3)).sum())
        clean = int((risk_df["flag_count"] == 0).sum())

        risk_bars = []
        max_flags = risk_df["flag_count"].max() or 1
        for _, r in risk_df.iterrows():
            dev_id = r["device_id"]
            fc = int(r["flag_count"])
            color = RISK_COLORS.get(r["risk_level"], "#2E7D32")
            cust = customer_map.get(device_customer_map.get(dev_id, ""), {}).get("name", "UNASSIGNED").upper()
            risk_bars.append({
                "label": device_names.get(dev_id, dev_id),
                "sub": cust,
                "value": f"{fc} / 5",
                "pct": round(fc / 5 * 100, 1),
                "color": color,
            })

        result.append({
            "type": "hbar",
            "title": f"At-Risk Vehicles (Last {months_label})",
            "icon": "emergency",
            "insight": ai_insights.get("risk",
                f"Each vehicle is scored 0–5 based on how many risk factors it triggers: "
                "Utilization Extreme | Unsafe Driving | Fault Codes | High Idling | Battery Drain. "
                f"{critical} Critical (≥4) and {high} High (3 factors) vehicles require immediate attention."),
            "bars": risk_bars,
            "thr1_pct": 60,
            "thr2_pct": 80,
            "metrics": [{"label": "Critical (4–5 factors)", "value": str(critical)},
                        {"label": "High (3 factors)", "value": str(high)},
                        {"label": "Medium (1–2 factors)", "value": str(medium)},
                        {"label": "Clean (0 factors)", "value": str(clean)}],
        })

        # At-risk by customer
        cust_risk: dict[str, dict] = {}
        for _, r in risk_df.iterrows():
            dev_id = r["device_id"]
            cust_id = device_customer_map.get(dev_id, "")
            cname = customer_map.get(cust_id, {}).get("name", "UNASSIGNED").upper()
            if cname not in cust_risk:
                cust_risk[cname] = {"at_risk": 0, "total": 0, "max_level": "OK"}
            cust_risk[cname]["total"] += 1
            if r["risk_level"] != "OK":
                cust_risk[cname]["at_risk"] += 1
            order = {"Critical": 0, "Warning": 1, "Monitor": 2, "OK": 3}
            if order.get(r["risk_level"], 3) < order.get(cust_risk[cname]["max_level"], 3):
                cust_risk[cname]["max_level"] = r["risk_level"]

        risk_cust_rows = []
        for cname, data in sorted(cust_risk.items(), key=lambda x: -x[1]["at_risk"]):
            level = data["max_level"]
            flag = "red" if level == "Critical" else ("orange" if level == "Warning" else ("yellow" if level == "Monitor" else "green"))
            risk_cust_rows.append({
                "cells": [cname, str(data["at_risk"]), str(data["total"]),
                          data["max_level"]],
                "flag": flag,
            })

        result.append({
            "type": "table",
            "title": "At-Risk Vehicles — Affected Groups",
            "icon": "emergency",
            "insight": ai_insights.get("risk_customers",
                f"At-risk vehicles are distributed across {len(cust_risk)} groups. "
                "Prioritise groups with the highest at-risk vehicle counts."),
            "cols": ["Group", "At-Risk Vehicles", "Total Vehicles", "Top Risk Flag"],
            "rows": risk_cust_rows,
            "metrics": [{"label": "At-Risk Vehicles", "value": str(critical + high + medium)},
                        {"label": "Affected Groups", "value": str(sum(1 for d in cust_risk.values() if d["at_risk"] > 0))}],
        })

    # ── 20. Recommendations ───────────────────────────────────────────────────
    if "recommendations" in slide_set:
        result.append({
            "type": "summary",
            "title": "Key Strategic Recommendations",
            "icon": "lightbulb",
            "insight": ai_insights.get("recommendations_intro",
                f"The following {len(recommendations)} recommendations are auto-generated from "
                f"{month_count} months of fleet data. Each insight is directly tied to a measurable data signal."),
            "recs": recommendations,
            "metrics": [{"label": "Insights", "value": str(len(recommendations))},
                        {"label": "Period", "value": months_label}],
        })

    # ── 21. Thanks ────────────────────────────────────────────────────────────
    result.append({"type": "thanks", "db_display": db_display})

    return result


def build_diagnostic_data(
    *,
    utilization_df: pd.DataFrame,
    idling_df: pd.DataFrame,
    safety_df: pd.DataFrame,
    battery_df: pd.DataFrame,
    fault_df: pd.DataFrame,
    exception_events: dict[str, list[dict]],
    rule_names: dict[str, str],
    device_names: dict[str, str],
    device_customer_map: dict[str, str],
    customer_map: dict[str, dict],
    battery_fault_data: list[dict],
    engine_fault_data: list[dict],
    diagnostic_map: dict[str, dict] | None = None,
) -> dict:
    """Build diagnostic data for CSV export."""
    diag: dict = {"vehicles": [], "battery_faults": [], "engine_faults": [], "safety_events": []}

    # Pre-compute safety event counts per device
    safety_event_counts: dict[str, int] = {}
    for events in exception_events.values():
        for ev in events:
            dev = ev.get("device", {})
            dev_id = dev.get("id") if isinstance(dev, dict) else dev
            if dev_id:
                safety_event_counts[dev_id] = safety_event_counts.get(dev_id, 0) + 1

    # Per-vehicle summary
    all_device_ids = set()
    if not utilization_df.empty:
        all_device_ids.update(utilization_df["device_id"].tolist())
    if not idling_df.empty:
        all_device_ids.update(idling_df["device_id"].tolist())

    for dev_id in sorted(all_device_ids):
        row = {"device_id": dev_id, "device_name": device_names.get(dev_id, dev_id)}
        cust_id = device_customer_map.get(dev_id, "")
        row["group"] = customer_map.get(cust_id, {}).get("name", "UNASSIGNED")

        # Utilization
        if not utilization_df.empty and dev_id in utilization_df["device_id"].values:
            u = utilization_df[utilization_df["device_id"] == dev_id].iloc[0]
            row["trip_count"] = int(u.get("trip_count", 0)) if "trip_count" in u else 0
            row["active_days"] = int(u.get("active_days", 0))
            row["distance_km"] = round(float(u.get("total_distance_km", 0)), 2)
            row["drive_hours"] = round(float(u.get("total_drive_hours", 0)), 2)
        else:
            row["trip_count"] = row["active_days"] = 0
            row["distance_km"] = row["drive_hours"] = 0.0

        # Idling - idle_hours from utilization (all vehicles), idle_cost from idling (fuel-configured only)
        if not utilization_df.empty and dev_id in utilization_df["device_id"].values:
            u = utilization_df[utilization_df["device_id"] == dev_id].iloc[0]
            row["idle_hours"] = round(float(u.get("total_idle_hours", 0)), 2)
        else:
            row["idle_hours"] = 0.0

        if not idling_df.empty and dev_id in idling_df["device_id"].values:
            i = idling_df[idling_df["device_id"] == dev_id].iloc[0]
            row["idle_cost"] = round(float(i.get("idle_cost", 0)), 2)
        else:
            row["idle_cost"] = 0.0

        # Safety
        if not safety_df.empty and dev_id in safety_df["device_id"].values:
            s = safety_df[safety_df["device_id"] == dev_id].iloc[0]
            row["safety_score"] = round(float(s.get("safety_score", 100)), 1)
        else:
            row["safety_score"] = 100.0
        row["safety_events"] = safety_event_counts.get(dev_id, 0)

        # Battery faults
        if not battery_df.empty and dev_id in battery_df["device_id"].values:
            b = battery_df[battery_df["device_id"] == dev_id].iloc[0]
            row["battery_faults"] = int(b.get("fault_count", 0))
        else:
            row["battery_faults"] = 0

        diag["vehicles"].append(row)

    # Helper to resolve diagnostic metadata
    diag_lookup = diagnostic_map or {}

    def resolve_diag(fd: dict) -> tuple[str, str, any]:
        """Extract diagnostic id, name, code from fault data, using resolved map."""
        diagnostic = fd.get("diagnostic", {})
        diag_id = diagnostic.get("id") if isinstance(diagnostic, dict) else ""

        # Try to get from resolved map first
        if diag_id and diag_id in diag_lookup:
            resolved = diag_lookup[diag_id]
            return (
                diag_id,
                resolved.get("name", ""),
                resolved.get("code"),
            )

        # Fallback to what's in the fault data
        diag_name = diagnostic.get("name") if isinstance(diagnostic, dict) else ""
        code = diagnostic.get("code") if isinstance(diagnostic, dict) else fd.get("code")
        return diag_id, diag_name, code

    # Battery fault events (raw)
    for fd in battery_fault_data:
        dev = fd.get("device", {})
        dev_id = dev.get("id") if isinstance(dev, dict) else dev
        diag_id, diag_name, code = resolve_diag(fd)
        dt = fd.get("dateTime", "")
        diag["battery_faults"].append({
            "device_id": dev_id,
            "device_name": device_names.get(dev_id, dev_id),
            "diagnostic_id": diag_id,
            "diagnostic_name": diag_name,
            "code": code,
            "date_time": dt,
        })

    # Engine fault events (raw)
    for fd in engine_fault_data:
        dev = fd.get("device", {})
        dev_id = dev.get("id") if isinstance(dev, dict) else dev
        diag_id, diag_name, code = resolve_diag(fd)
        controller = fd.get("controller", {})
        ctrl_id = controller.get("id") if isinstance(controller, dict) else ""
        dt = fd.get("dateTime", "")
        diag["engine_faults"].append({
            "device_id": dev_id,
            "device_name": device_names.get(dev_id, dev_id),
            "diagnostic_id": diag_id,
            "diagnostic_name": diag_name,
            "code": code,
            "controller_id": ctrl_id,
            "date_time": dt,
        })

    # Safety events (raw)
    for rule_id, events in exception_events.items():
        rule_name = rule_names.get(rule_id, rule_id)
        for ev in events:
            dev = ev.get("device", {})
            dev_id = dev.get("id") if isinstance(dev, dict) else dev
            dt = ev.get("activeFrom", "")
            duration = ev.get("duration", "")
            diag["safety_events"].append({
                "device_id": dev_id,
                "device_name": device_names.get(dev_id, dev_id),
                "rule_id": rule_id,
                "rule_name": rule_name,
                "date_time": dt,
                "duration": duration,
            })

    return diag


def build_html_report(
    slides: list[dict],
    db_display: str,
    currency: str = "USD",
    diagnostic_data: dict | None = None,
) -> str:
    """Inject slides JSON and diagnostic data into the HTML template."""
    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    slides_json = json.dumps(slides, ensure_ascii=False, default=str)
    diag_json = json.dumps(diagnostic_data or {}, ensure_ascii=False, default=str)
    html = (
        template
        .replace("__SLIDES_JSON__", slides_json)
        .replace("__DIAG_DATA__", diag_json)
        .replace("__DB_DISPLAY__", db_display)
        .replace("__CURRENCY__", currency)
    )
    return html
