"""Act-gate endpoints. Proposing a dry-run is open; approving/rejecting is an ACT
that requires an authenticated human (the identity gate) and is audited."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..services import apply

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def _require_user(request: Request) -> str:
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="sign in to perform this action")
    return user["email"]


class ApplyRequest(BaseModel):
    domain: str
    network: str


@router.get("")
def list_workflows(state: Optional[str] = None):
    return apply.list_runs(state)


@router.post("/apply")
def propose_apply(req: ApplyRequest, request: Request):
    user = request.session.get("user")
    by = user["email"] if user else "console"
    result = apply.create_apply_run(req.domain, req.network, created_by=by)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/{run_id}/approve")
def approve(run_id: int, request: Request):
    approver = _require_user(request)
    result = apply.approve_run(run_id, approver)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


class RejectRequest(BaseModel):
    reason: str = ""


@router.post("/{run_id}/reject")
def reject(run_id: int, request: Request, body: Optional[RejectRequest] = None):
    actor = _require_user(request)
    return apply.reject_run(run_id, actor, (body.reason if body else ""))
