"""SSE progress streaming router: GET /api/progress/{job_id}"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.jobs.store import get_job

router = APIRouter()

POLL_INTERVAL = 0.4  # seconds


async def _event_stream(job_id: str):
    """Async generator yielding SSE frames for a job until it finishes.

    Polls the job's ``pending_events`` buffer every POLL_INTERVAL seconds,
    forwarding each buffered ProgressEvent as an SSE ``data:`` frame, and stops
    once the job status reaches a terminal state ("done" or "error"). Yields a
    single error frame if the job id is unknown.
    """
    job = get_job(job_id)
    if job is None:
        yield 'data: {"type":"error","message":"Job not found"}\n\n'
        return

    # Phase 1: poll-and-drain loop. Flush whatever is buffered, then stop once the
    # job has reached a terminal state.
    while True:
        while job.pending_events:
            ev = job.pending_events.pop(0)
            yield ev.to_sse()

        if job.status in ("done", "error"):
            break

        await asyncio.sleep(POLL_INTERVAL)

    # Phase 2: final drain. There is a race between appending the last events and
    # the status flipping to done/error — the pipeline can push the terminal
    # (done/error) event AFTER phase 1 last checked the buffer but at the same time
    # it sets the status. Draining once more here guarantees those trailing events
    # are delivered and never dropped.
    while job.pending_events:
        ev = job.pending_events.pop(0)
        yield ev.to_sse()


@router.get("/api/progress/{job_id}")
async def stream_progress(job_id: str):
    """SSE endpoint that streams live generation progress for a job.

    Returns 404 if the job is unknown; otherwise a ``text/event-stream`` response
    backed by _event_stream(). The client watches this to drive the progress
    overlay (see USER_GUIDE.md "Generating & Downloading the Report").
    """
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return StreamingResponse(
        _event_stream(job_id),
        media_type="text/event-stream",
        # Anti-buffering headers so progress arrives in real time rather than in
        # one lump at the end:
        #   Cache-Control: no-cache   — stop browsers/proxies caching the stream.
        #   X-Accel-Buffering: no     — tell nginx (if fronting the app) not to
        #                               buffer the response, which would otherwise
        #                               hold events until the connection closes.
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
