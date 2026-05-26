"""Report download router: GET /api/download/{job_id}"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.jobs.store import get_job

router = APIRouter()


@router.get("/api/download/{job_id}")
async def download_report(job_id: str):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "done" or not job.result_html:
        raise HTTPException(status_code=409, detail="Report not ready")

    filename = f"fleet_insights_{job.request.get('group_name', 'report').replace(' ', '_')}.html"
    return Response(
        content=job.result_html.encode("utf-8"),
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
