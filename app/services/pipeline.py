"""Generation pipeline: orchestrates all analytics + AI steps."""
from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import date

from app.config import settings
from app.jobs.store import JobState, emit
from app.services.ai_insights import generate_all_insights
from app.services.analytics.battery import BATTERY_DIAG_IDS, compute_battery_health
from app.services.analytics.faults import compute_fault_codes
from app.services.analytics.fleet import (
    aggregate_fuel_type_counts,
    build_group_children,
    detect_fuel_types,
    get_devices_in_group,
)
from app.services.analytics.idling import compute_idling
from app.services.analytics.risk import compute_at_risk
from app.services.analytics.safety import compute_safety_scores
from app.services.analytics.utilization import (
    build_trips_dataframe,
    compute_active_days,
    compute_max_speeding,
    compute_monthly_kpis,
    compute_utilization_composite,
    extract_gps_points,
)
from app.services.geotab import GeotabClient
from app.services.report_builder import build_diagnostic_data, build_html_report, build_slides_list

logger = logging.getLogger(__name__)


async def run_generation_pipeline(job: JobState) -> None:
    """Main pipeline coroutine. Emits SSE progress events and sets job.result_html."""
    creds = job.credentials
    req = job.request

    group_id: str = req["group_id"]
    group_name: str = req["group_name"]
    start_date: date = date.fromisoformat(req["start_date"])
    end_date: date = date.fromisoformat(req["end_date"])
    language: str = req.get("language", "en")
    currency: str = req.get("currency", "USD")
    slides: list[str] = req["slides"]
    safety_rules: list[dict] = req["safety_rules"]
    fuel_settings: list[dict] = req["fuel_settings"]

    db = creds.get("database", "")
    db_display = db.upper()

    job.status = "running"
    client = GeotabClient.from_credentials(creds)

    try:
        # Step 1: Authenticate
        emit(job, "auth", "Authenticating with MyGeotab...")
        await client.authenticate()
        emit(job, "auth", "Authenticated successfully.", done=True)

        # Step 2: Devices + groups
        emit(job, "devices", "Fetching fleet devices and groups...")
        devices_raw, groups_raw = await asyncio.gather(
            client.get_devices(),
            client.get_groups(),
        )
        group_devices = get_devices_in_group(group_id, devices_raw, groups_raw)
        device_ids = {d["id"] for d in group_devices}
        device_names = {d["id"]: d.get("name") or d["id"] for d in group_devices}
        device_fuel_map = detect_fuel_types(group_devices, groups_raw)

        # Build customer → device mapping
        # Each device may be in multiple sub-groups; map device → first matching customer sub-group
        from app.services.analytics.fleet import build_group_children, get_subtree_group_ids, discover_customers
        children = build_group_children(groups_raw)
        customer_map = discover_customers(groups_raw, devices_raw)

        # Build device → customer lookup (skip GroupCompanyId — root-only devices stay
        # unmapped and are rendered as UNASSIGNED in the portfolio slide)
        device_customer_map: dict[str, str] = {}
        for dev in group_devices:
            dev_id = dev["id"]
            dev_gids = {g.get("id") if isinstance(g, dict) else g for g in dev.get("groups", [])}
            for cust_id in customer_map:
                if cust_id == "GroupCompanyId":
                    continue
                subtree = get_subtree_group_ids(cust_id, children)
                if dev_gids & subtree:
                    device_customer_map[dev_id] = cust_id
                    break

        emit(job, "devices", f"{len(group_devices)} vehicles loaded.", done=True)

        # Step 3: Trips
        emit(job, "trips", "Fetching trip data...")
        trips_raw = await client.get_trips(start_date, end_date)
        trips_df = build_trips_dataframe(trips_raw, device_ids, start_date, end_date)
        emit(job, "trips", f"{len(trips_df)} trips loaded.", done=True)

        # Step 4: Utilization
        emit(job, "utilization", "Computing utilization metrics...")
        active_df = compute_active_days(trips_df, device_ids, start_date, end_date)
        monthly_df = compute_monthly_kpis(trips_df)
        utilization_df = compute_utilization_composite(active_df, trips_df)
        gps_points = extract_gps_points(trips_df)
        max_speeding_df = compute_max_speeding(trips_df, device_names)
        emit(job, "utilization", "Utilization computed.", done=True)

        # Step 5: Idling
        emit(job, "idling", "Computing idling costs...")
        idling_df = compute_idling(trips_df, device_fuel_map, fuel_settings)
        emit(job, "idling", "Idling computed.", done=True)

        # Step 6: Safety
        emit(job, "safety", "Fetching safety exception events...")
        # Resolve rule names first
        rule_names: dict[str, str] = {}
        for rule in safety_rules:
            rid = rule["rule_id"]
            rule_obj = await client.get_rule(rid)
            if rule_obj:
                rule_names[rid] = rule_obj.get("name") or rid

        exception_events: dict[str, list[dict]] = {}
        for rule in safety_rules:
            rid = rule["rule_id"]
            emit(job, "safety", f"Fetching events for rule {rule_names.get(rid, rid)}...")
            events = await client.get_exception_events_feed(rid, start_date, end_date)
            exception_events[rid] = events

        safety_df = compute_safety_scores(exception_events, safety_rules, rule_names, trips_df)
        emit(job, "safety", f"{sum(len(v) for v in exception_events.values())} events processed.", done=True)

        # Step 7: Battery (fetch raw data only)
        emit(job, "battery", "Fetching battery diagnostics...")
        status_data = await client.get_status_data(BATTERY_DIAG_IDS, start_date, end_date)
        battery_fault_data = await client.get_battery_fault_data(start_date, end_date)
        emit(job, "battery", f"{len(battery_fault_data)} battery fault events loaded.", done=True)

        # Step 8: Engine faults (fetch raw data only)
        emit(job, "faults", "Fetching engine fault codes...")
        engine_fault_data = await client.get_engine_fault_data(start_date, end_date)
        emit(job, "faults", f"{len(engine_fault_data)} engine fault events loaded.", done=True)

        # Step 8b: Resolve diagnostic metadata so analytics can use codes/names
        emit(job, "faults", "Resolving fault diagnostic codes...")
        all_diag_ids = set()
        for fd in battery_fault_data:
            diag = fd.get("diagnostic", {})
            if isinstance(diag, dict) and diag.get("id"):
                all_diag_ids.add(diag["id"])
        for fd in engine_fault_data:
            diag = fd.get("diagnostic", {})
            if isinstance(diag, dict) and diag.get("id"):
                all_diag_ids.add(diag["id"])
        diagnostic_map = await client.resolve_diagnostics_bulk(list(all_diag_ids))
        emit(job, "faults", f"Resolved {len(diagnostic_map)} diagnostic codes.", done=True)

        # Step 8c: Enrich fault records with resolved diagnostic metadata, then analyze
        def _enrich(fd: dict) -> dict:
            diag = fd.get("diagnostic", {})
            diag_id = diag.get("id") if isinstance(diag, dict) else diag
            if diag_id and diag_id in diagnostic_map:
                resolved = diagnostic_map[diag_id]
                merged = dict(diag) if isinstance(diag, dict) else {"id": diag_id}
                if resolved.get("code") is not None:
                    merged["code"] = resolved["code"]
                if resolved.get("name"):
                    merged["name"] = resolved["name"]
                fd = dict(fd)
                fd["diagnostic"] = merged
            return fd

        battery_fault_data = [_enrich(fd) for fd in battery_fault_data]
        engine_fault_data = [_enrich(fd) for fd in engine_fault_data]

        battery_df = compute_battery_health(status_data, battery_fault_data, device_ids)
        fault_df = compute_fault_codes(engine_fault_data, device_ids)
        emit(job, "faults", f"{int(fault_df['count'].sum()) if not fault_df.empty else 0} DTC fault events processed.", done=True)

        # Step 9: Risk
        emit(job, "risk", "Computing at-risk vehicle matrix...")
        risk_df = compute_at_risk(utilization_df, idling_df, safety_df, device_names)
        emit(job, "risk", "Risk matrix complete.", done=True)

        # Step 10: AI insights
        emit(job, "ai", "Generating AI insights...")
        # Build fleet summary for LLM context
        total_events = sum(len(v) for v in exception_events.values())
        fleet_summary = {
            "group_name": group_name,
            "database": db_display,
            "period": f"{start_date} to {end_date}",
            "currency": currency,
            "total_vehicles": len(group_devices),
            "customer_groups": len(customer_map),
            "total_trips": len(trips_df),
            "total_distance_km": round(trips_df["distance_km"].sum(), 0) if not trips_df.empty else 0,
            "total_idle_hours": round(trips_df["idle_hours"].sum(), 1) if not trips_df.empty else 0,
            "total_idle_cost": f"{currency} {round(idling_df['idle_cost'].sum(), 0)}" if not idling_df.empty else f"{currency} 0",
            "total_safety_events": total_events,
            "high_risk_vehicles": int((safety_df["safety_score"] < settings.SAFETY_HIGH_RISK).sum()) if not safety_df.empty else 0,
            "battery_fault_events": int(battery_df["fault_count"].sum()) if not battery_df.empty else 0,
            "at_risk_vehicles": int((risk_df["flag_count"] > 0).sum()) if not risk_df.empty else 0,
        }
        ai_insights, recommendations = await generate_all_insights(fleet_summary, slides + ["recommendations_intro"], language)
        emit(job, "ai", "AI insights generated.", done=True)

        # Step 11: Render
        emit(job, "render", "Building HTML report...")
        slide_list = build_slides_list(
            db=db,
            db_display=db_display,
            group_name=group_name,
            currency=currency,
            start_date=start_date,
            end_date=end_date,
            slides=slides,
            utilization_df=utilization_df,
            monthly_df=monthly_df,
            idling_df=idling_df,
            safety_df=safety_df,
            rule_names=rule_names,
            safety_rules=safety_rules,
            exception_events=exception_events,
            battery_df=battery_df,
            fault_df=fault_df,
            risk_df=risk_df,
            gps_points=gps_points,
            customer_map=customer_map,
            device_customer_map=device_customer_map,
            device_names=device_names,
            ai_insights=ai_insights,
            recommendations=recommendations,
            battery_fault_data=battery_fault_data,
            engine_fault_data=engine_fault_data,
            max_speeding_df=max_speeding_df,
        )
        diagnostic_data = build_diagnostic_data(
            utilization_df=utilization_df,
            idling_df=idling_df,
            safety_df=safety_df,
            battery_df=battery_df,
            fault_df=fault_df,
            exception_events=exception_events,
            rule_names=rule_names,
            device_names=device_names,
            device_customer_map=device_customer_map,
            customer_map=customer_map,
            battery_fault_data=battery_fault_data,
            engine_fault_data=engine_fault_data,
            diagnostic_map=diagnostic_map,
        )
        html = build_html_report(slide_list, db_display, currency, diagnostic_data)
        job.result_html = html
        job.status = "done"
        emit(job, "render", "Report ready.", done=True)
        job.pending_events.append(_done_event())

    except Exception as exc:
        logger.error("Pipeline error for job %s: %s", job.job_id, traceback.format_exc())
        job.status = "error"
        job.error = str(exc)
        emit(job, "error", f"Generation failed: {exc}", done=True)
        job.pending_events.append(_error_event(str(exc)))


def _done_event():
    import json
    from app.jobs.store import ProgressEvent
    ev = ProgressEvent(step="done", message="Report generation complete.", done=True)
    ev.to_sse = lambda: f'data: {json.dumps({"type": "done", "step": "done", "message": "complete"})}\n\n'
    return ev


def _error_event(msg: str):
    import json
    from app.jobs.store import ProgressEvent
    ev = ProgressEvent(step="error", message=msg, done=True)
    ev.to_sse = lambda: f'data: {json.dumps({"type": "error", "step": "error", "message": msg})}\n\n'
    return ev


async def create_job_and_start(
    job_id: str,
    credentials: dict,
    request: dict,
) -> None:
    """Create a job in the store and launch the pipeline as a background task."""
    from app.jobs.store import create_job
    job = create_job(job_id, credentials, request)
    asyncio.create_task(run_generation_pipeline(job))
