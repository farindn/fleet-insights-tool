"""Diagnostic export router: GET /api/download/{job_id}/diagnostics.zip"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.jobs.store import get_job
from app.services.diagnostics_export import build_diagnostics_zip, report_basename

router = APIRouter()


@router.get("/api/download/{job_id}/diagnostics.zip")
async def download_diagnostics_zip(job_id: str):
    """Return the job's diagnostic data as a ZIP of four CSVs.

    The archive holds the per-vehicle summary plus the raw safety, battery, and
    engine fault events (``Fleet Insights_<DB>_<period>_<kind>.csv``) — the same
    data the report used to embed for its in-browser CSV export, now built
    server-side so the shared HTML report stays small.

    Mirrors ``/api/download/{job_id}``'s guards and posture: 404 if the job is
    unknown, 409 if generation has not finished. Unauthenticated by design —
    access is gated by the unguessable ``job_id`` and the job TTL, and it exposes
    no data the report download did not already serve. An empty fleet yields
    header-only CSVs rather than an error.
    """
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "done":
        raise HTTPException(status_code=409, detail="Report not ready")

    base = report_basename(job)
    return Response(
        content=build_diagnostics_zip(job.diagnostic_data or {}, base),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{base}_diagnostics.zip"'},
    )
