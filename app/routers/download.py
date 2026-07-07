"""Report download router: GET /api/download/{job_id}"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.jobs.store import get_job

router = APIRouter()


def _yymmdd(iso: str) -> str:
    """'2026-01-31' → '260131' (drop the century, strip dashes)."""
    return iso[2:].replace("-", "") if iso else ""


@router.get("/api/download/{job_id}")
async def download_report(job_id: str):
    """Return the finished HTML report as a file download.

    Responds 404 if the job is unknown, or 409 if generation has not finished
    (status != "done"). The Content-Disposition filename matches the
    user-facing name the SPA assigns (static/app.js) and the pattern in
    USER_GUIDE.md → Generating & Downloading the Report:
    ``Fleet Insights_<DATABASE>_<YYMMDD-YYMMDD>.html``.
    """
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    # Report is only available once the pipeline has completed successfully.
    if job.status != "done" or not job.result_html:
        raise HTTPException(status_code=409, detail="Report not ready")

    # Reconstruct the documented filename from the database (credentials) and
    # the analysis window (request); each part degrades gracefully if missing.
    db = (job.credentials.get("database") or "report").upper()
    period = f"{_yymmdd(job.request.get('start_date', ''))}-{_yymmdd(job.request.get('end_date', ''))}"
    filename = f"Fleet Insights_{db}_{period}.html"
    return Response(
        content=job.result_html.encode("utf-8"),
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
