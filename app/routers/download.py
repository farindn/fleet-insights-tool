"""Report download router: GET /api/download/{job_id}"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.jobs.store import get_job
from app.services.diagnostics_export import report_basename

router = APIRouter()


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

    # Filename convention is centralised in diagnostics_export.report_basename so
    # the HTML report and the diagnostics ZIP always share the same name stem.
    filename = f"{report_basename(job)}.html"
    return Response(
        content=job.result_html.encode("utf-8"),
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
