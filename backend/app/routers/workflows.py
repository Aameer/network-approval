"""Act-gate endpoints. Proposing a dry-run is open; approving/rejecting is an ACT
that requires an authenticated human (the identity gate) and is audited."""
from __future__ import annotations

import json
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
    operation: Optional[str] = None  # create|update — inferred from application status if omitted


@router.get("")
def list_workflows(state: Optional[str] = None):
    return apply.list_runs(state)


@router.post("/apply")
def propose_apply(req: ApplyRequest, request: Request):
    """Prepare the reconcile answer sheet (scout schema -> resolve from our DB -> gated run)."""
    from ..services import pipeline
    user = request.session.get("user")
    by = user["email"] if user else "console"
    op = req.operation or pipeline.infer_operation(req.domain, req.network)
    result = pipeline.prepare(req.domain, req.network, operation=op, created_by=by)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/{run_id}/approve")
def approve(run_id: int, request: Request, test: bool = False):
    # test=true runs ONE real Skyvern submission (force-live) without flipping SKYVERN_LIVE globally.
    approver = _require_user(request)
    result = apply.approve_run(run_id, approver, force_live=test)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


class RejectRequest(BaseModel):
    reason: str = ""


@router.post("/{run_id}/reject")
def reject(run_id: int, request: Request, body: Optional[RejectRequest] = None):
    actor = _require_user(request)
    return apply.reject_run(run_id, actor, (body.reason if body else ""))


# --- single-page review: one run, all its fields under one id ---

@router.get("/{run_id}/answers")
def get_answers(run_id: int):
    """The whole sheet for one run — run meta + every field row (for the review page)."""
    from sqlmodel import Session, select
    from ..db import engine
    from ..models import RunAnswer, WorkflowRun
    from ..services import pipeline
    defaults = pipeline.defaults_for_run(run_id)  # for the per-field "Revert to default"
    with Session(engine) as s:
        run = s.get(WorkflowRun, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="run not found")
        rows = s.exec(select(RunAnswer).where(RunAnswer.run_id == run_id)
                      .order_by(RunAnswer.page, RunAnswer.id)).all()
        import json as _json
        _res = _json.loads(run.result or "{}")
        return {
            "run": {"id": run.id, "site": run.site_domain, "network": run.network_name,
                    "operation": run.operation, "kind": run.kind, "state": run.state,
                    "unverified": _res.get("unverified") or []},
            "answers": [{"id": r.id, "page": r.page, "label": r.label, "field_key": r.field_key,
                         "value": r.value, "current_value": r.current_value, "status": r.status,
                         "source": r.source, "required": r.required, "changed": r.changed,
                         "default": defaults.get(r.field_key)}
                        for r in rows],
        }


class AnswerEdit(BaseModel):
    updates: dict  # {answer_id: new_value}


@router.patch("/{run_id}/answers")
def patch_answers(run_id: int, body: AnswerEdit, request: Request):
    """Save inline edits to the sheet (overrides). Audited."""
    from sqlmodel import Session
    from ..db import engine
    from ..models import AuditLog, RunAnswer
    actor = _require_user(request)
    import json
    from ..models import WorkflowRun
    n = 0
    with Session(engine) as s:
        for aid, val in body.updates.items():
            row = s.get(RunAnswer, int(aid))
            if row and row.run_id == run_id and row.field_key not in ("password", "password_confirm"):
                row.value = val if (val is None or str(val).strip()) else None
                s.add(row)
                n += 1
        # Editing invalidates a prior approval — the sheet must be re-approved before LIVE execute.
        run = s.get(WorkflowRun, run_id)
        reset = False
        if n and run and run.state == "approved":
            run.state = "awaiting_approval"
            s.add(run)
            reset = True
        s.add(AuditLog(actor=actor, actor_kind="human", action="sheet.edited",
                       target=f"run:{run_id}", detail=json.dumps({"fields": n, "approval_reset": reset})))
        s.commit()
    return {"run_id": run_id, "updated": n, "approval_reset": reset}


@router.post("/{run_id}/execute")
def execute(run_id: int, request: Request, live: bool = False):
    """Execute the sheet. Dry-run by default; live=true fires the real browser submission."""
    actor = _require_user(request)
    result = apply.execute_run(run_id, actor, force_live=live)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/{run_id}/live")
def run_live(run_id: int):
    """Live activity feed for a run — proxies Skyvern's step-by-step action log so the review
    page can show what the agent is doing right now (+ the recording link when it exists)."""
    import httpx
    from sqlmodel import Session
    from ..db import engine
    from ..models import WorkflowRun
    from ..config import SKYVERN_API_KEY, SKYVERN_BASE_URL
    with Session(engine) as s:
        run = s.get(WorkflowRun, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="run not found")
        state = run.state
        rid = json.loads(run.result or "{}").get("run_id")
    if not rid:
        return {"state": state, "skyvern": None, "actions": [], "recording": None}
    base = SKYVERN_BASE_URL.rstrip("/"); h = {"x-api-key": SKYVERN_API_KEY}
    try:
        with httpx.Client(timeout=15) as c:
            t = c.get(f"{base}/api/v1/tasks/{rid}", headers=h).json()
            acts = c.get(f"{base}/api/v1/tasks/{rid}/actions", headers=h).json()
    except Exception:  # noqa: BLE001
        return {"state": state, "skyvern": None, "actions": [], "recording": None}
    steps = [{"status": a.get("status"), "type": a.get("action_type"),
              "reasoning": a.get("reasoning")} for a in (acts or [])]
    return {"state": state, "skyvern": t.get("status"), "actions": steps,
            "recording": t.get("recording_url")}


@router.get("/{run_id}/status")
def run_status(run_id: int):
    """Live status of a run. If it's executing on the network, poll Skyvern (and, when the run
    finishes, run write-back). Lets the UI show what's running and what finished."""
    from sqlmodel import Session
    from ..db import engine
    from ..models import WorkflowRun
    with Session(engine) as s:
        run = s.get(WorkflowRun, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="run not found")
        state = run.state
    skyvern = None
    written_back = None
    if state in ("executing", "running"):
        fin = apply.finalize_execute(run_id)  # polls; on terminal -> state+write-back
        skyvern = fin.get("status")
        written_back = fin.get("written_back")
        with Session(engine) as s:
            state = s.get(WorkflowRun, run_id).state
    return {"run_id": run_id, "state": state, "skyvern": skyvern, "written_back": written_back}
