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
    job_id = str(uuid.uuid4())
    request_dict = body.model_dump(mode="json")
    # Convert dates to ISO strings for JSON serialisation in store
    request_dict["start_date"] = str(body.start_date)
    request_dict["end_date"] = str(body.end_date)
    # Serialise nested models
    request_dict["safety_rules"] = [r.model_dump() for r in body.safety_rules]
    request_dict["fuel_settings"] = [f.model_dump() for f in body.fuel_settings]

    await create_job_and_start(job_id, creds, request_dict)
    return GenerateResponse(job_id=job_id)
