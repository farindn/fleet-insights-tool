"""In-memory job store. No database — single-process, personal tool."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


# ---------------------------------------------------------------------------
# SSE JSON contract (single source of truth for what the frontend consumes)
# ---------------------------------------------------------------------------
# Every progress message streamed to the browser is a JSON object with a
# ``type`` discriminator drawn from a fixed vocabulary:
#   - "step"  — an in-progress/step-complete update (emitted by ProgressEvent
#               below); carries ``step`` (stage id), ``message`` (human text),
#               and ``done`` (bool: is this stage finished).
#   - "done"  — terminal event: the whole generation finished successfully.
#   - "error" — terminal event: generation failed; ``message`` holds the reason.
# The "done"/"error" terminal events are produced in app/services/pipeline.py
# (_done_event / _error_event) by overriding to_sse on a ProgressEvent instance.
# app/routers/progress.py serialises these onto the wire as ``data: <json>\n\n``.
@dataclass
class ProgressEvent:
    """A single ``type: "step"`` progress update in the SSE stream.

    Fields map directly onto the JSON payload: ``step`` is the stage identifier
    (e.g. "auth", "trips", "render"), ``message`` is the human-readable status
    text, and ``done`` marks whether this stage has completed.
    """
    step: str
    message: str
    done: bool = False

    def to_sse(self) -> str:
        """Serialise this event to a Server-Sent Events ``data:`` frame.

        Always emits ``type: "step"``; the terminal "done"/"error" frames are
        produced by the overrides in pipeline.py (see the contract comment above).
        """
        import json
        data = json.dumps({"type": "step", "step": self.step,
                           "message": self.message, "done": self.done})
        return f"data: {data}\n\n"


@dataclass
class JobState:
    """Full server-side state for one report-generation job.

    Holds the caller's ``credentials`` and ``request`` inputs, the live
    ``status``, a FIFO buffer of ``pending_events`` drained by the SSE stream,
    and the eventual ``result_html`` (or ``error``).

    ``created_at`` uses naive UTC (``datetime.utcnow``) to match the cleanup
    comparison in cleanup_old_jobs(); it is a TTL bookkeeping timestamp only,
    never serialised to clients.
    """
    job_id: str
    status: Literal["pending", "running", "done", "error"] = "pending"
    credentials: dict = field(default_factory=dict)
    request: dict = field(default_factory=dict)
    pending_events: list[ProgressEvent] = field(default_factory=list)
    result_html: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


# Process-local, in-memory job registry: not persisted and not shared across
# workers. Restarting the app (or running under multiple worker processes) loses
# all jobs — acceptable for this single-process personal tool (see module docstring).
_store: dict[str, JobState] = {}


def create_job(job_id: str, credentials: dict, request: dict) -> JobState:
    """Create and register a new JobState in the process-local store; return it."""
    job = JobState(job_id=job_id, credentials=credentials, request=request)
    _store[job_id] = job
    return job


def get_job(job_id: str) -> JobState | None:
    """Look up a job by id; returns None if unknown (or already cleaned up)."""
    return _store.get(job_id)


def emit(job: JobState, step: str, message: str, done: bool = False) -> None:
    """Append a ``type: "step"`` progress event to the job's buffer.

    The pipeline calls this to report stage progress; app/routers/progress.py
    drains ``job.pending_events`` and streams each one to the client.
    """
    job.pending_events.append(ProgressEvent(step=step, message=message, done=done))


async def cleanup_old_jobs(ttl_hours: int) -> None:
    """Background task: remove jobs older than ttl_hours."""
    while True:
        await asyncio.sleep(3600)
        cutoff = datetime.utcnow()
        stale = [
            jid for jid, j in list(_store.items())
            if (cutoff - j.created_at).total_seconds() > ttl_hours * 3600
        ]
        for jid in stale:
            _store.pop(jid, None)
