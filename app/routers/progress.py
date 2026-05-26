"""SSE progress streaming router: GET /api/progress/{job_id}"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.jobs.store import get_job

router = APIRouter()

POLL_INTERVAL = 0.4  # seconds


async def _event_stream(job_id: str):
    job = get_job(job_id)
    if job is None:
        yield 'data: {"type":"error","message":"Job not found"}\n\n'
        return

    while True:
        while job.pending_events:
            ev = job.pending_events.pop(0)
            yield ev.to_sse()

        if job.status in ("done", "error"):
            break

        await asyncio.sleep(POLL_INTERVAL)

    # Drain any remaining events
    while job.pending_events:
        ev = job.pending_events.pop(0)
        yield ev.to_sse()


@router.get("/api/progress/{job_id}")
async def stream_progress(job_id: str):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return StreamingResponse(
        _event_stream(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
