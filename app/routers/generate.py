"""Report generation router: POST /api/generate"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.routers.deps import get_credentials
from app.schemas.generate import GenerateRequest, GenerateResponse
from app.services.pipeline import create_job_and_start

router = APIRouter()


@router.post("/api/generate", response_model=GenerateResponse, status_code=202)
async def generate_report(
    body: GenerateRequest,
    creds: dict = Depends(get_credentials),
):
    """Kick off report generation and return immediately (async, non-blocking).

    Responds 202 Accepted with a ``job_id`` and starts the analytics/AI/render
    pipeline as a background task. The client then follows progress over SSE and
    downloads the finished report (see USER_GUIDE.md "Generating & Downloading
    the Report").
    """
    job_id = str(uuid.uuid4())
    request_dict = body.model_dump(mode="json")
    # Re-stringify the dates explicitly: although model_dump(mode="json") already
    # coerces date fields, we overwrite with str(...) to guarantee a plain
    # "YYYY-MM-DD" string in the stored request. The pipeline reads these back via
    # date.fromisoformat(), so a stable ISO string is required regardless of any
    # custom field serialisation on the schema.
    request_dict["start_date"] = str(body.start_date)
    request_dict["end_date"] = str(body.end_date)
    # Serialise nested models
    request_dict["safety_rules"] = [r.model_dump() for r in body.safety_rules]
    request_dict["fuel_settings"] = [f.model_dump() for f in body.fuel_settings]

    await create_job_and_start(job_id, creds, request_dict)
    return GenerateResponse(job_id=job_id)
