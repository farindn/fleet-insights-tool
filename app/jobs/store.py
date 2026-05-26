"""In-memory job store. No database — single-process, personal tool."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


@dataclass
class ProgressEvent:
    step: str
    message: str
    done: bool = False

    def to_sse(self) -> str:
        import json
        data = json.dumps({"type": "step", "step": self.step,
                           "message": self.message, "done": self.done})
        return f"data: {data}\n\n"


@dataclass
class JobState:
    job_id: str
    status: Literal["pending", "running", "done", "error"] = "pending"
    credentials: dict = field(default_factory=dict)
    request: dict = field(default_factory=dict)
    pending_events: list[ProgressEvent] = field(default_factory=list)
    result_html: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


# Global store
_store: dict[str, JobState] = {}


def create_job(job_id: str, credentials: dict, request: dict) -> JobState:
    job = JobState(job_id=job_id, credentials=credentials, request=request)
    _store[job_id] = job
    return job


def get_job(job_id: str) -> JobState | None:
    return _store.get(job_id)


def emit(job: JobState, step: str, message: str, done: bool = False) -> None:
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
