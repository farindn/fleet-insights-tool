"""FastAPI application factory."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.jobs.store import cleanup_old_jobs
from app.routers import auth, download, fleet, generate, progress

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan hook.

    On startup, launches the background ``cleanup_old_jobs`` task that evicts
    expired jobs from the in-memory store. On shutdown (after ``yield``), cancels
    that task so the event loop can exit cleanly.
    """
    task = asyncio.create_task(cleanup_old_jobs(settings.JOB_TTL_HOURS))
    yield
    task.cancel()


app = FastAPI(
    title="Fleet Insights Tool",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    # Wide-open CORS is acceptable here: this is a local, single-user tool that
    # runs on the user's own machine (see USER_GUIDE.md "Installation & Setup"),
    # not a shared/public service.
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(auth.router)
app.include_router(fleet.router)
app.include_router(generate.router)
app.include_router(progress.router)
app.include_router(download.router)

# Serve SPA from static/
# ``import os`` is kept local to this block since it is only needed for the
# static-file mount below and nowhere else in the module.
import os
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
# Mount the built single-page app at the root only if the static/ directory
# actually exists. This keeps the API usable (routers still work) in dev setups
# where the frontend has not been built yet, and mounting at "/" must come last
# so it does not shadow the /api routers registered above.
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
