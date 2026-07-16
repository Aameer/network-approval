"""C3 — Central Command & Control (PoC) — FastAPI entrypoint.

Run:  uvicorn app.main:app --reload --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .config import FRONTEND_ORIGIN, SESSION_SECRET
from .db import init_db
from .routers import audit, auth, copilot, inbox, jobs, networks, portfolio, registry, vault, workflows

app = FastAPI(title="C3 — Central Command & Control (PoC)")

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup():
    init_db()
    from .services import jobs as _jobs
    app.state.scheduler = _jobs.start_scheduler()


@app.get("/health")
def health():
    return {"status": "ok", "service": "c3-poc"}


app.include_router(auth.router)
app.include_router(portfolio.router)
app.include_router(audit.router)
app.include_router(copilot.router)
app.include_router(workflows.router)
app.include_router(registry.router)
app.include_router(vault.router)
app.include_router(jobs.router)
app.include_router(inbox.router)
app.include_router(networks.router)
