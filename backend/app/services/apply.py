"""The act-gate: prepare (scout->resolve) -> human approves -> execute -> write-back -> audit.

Reconcile-pipeline runs (kind='apply', operation set) are gated by approve_prepared and executed
from the sheet by execute_run; write-back on success converges our records. approval_flip runs
(parser-detected approvals) flip a NetworkApplication to approved. The old non-reconcile signup
path has been retired.
"""
from __future__ import annotations

import json
from datetime import date

from sqlalchemy import func
from sqlmodel import Session, select

from ..db import engine
from ..models import ApplicationStatus, AuditLog, NetworkApplication, Site, WorkflowRun


def approve_run(run_id: int, approver: str, force_live: bool = False) -> dict:
    with Session(engine) as s:
        run = s.get(WorkflowRun, run_id)
        if not run:
            return {"error": "workflow not found"}
        if run.state != "awaiting_approval":
            return {"error": f"workflow is '{run.state}', not awaiting_approval"}

        # Prepared reconcile runs are gate-only here (approve → mark approved, no execute).
        if run.operation:
            return approve_prepared(run_id, approver)

        # Parser-detected approval flip: mark the application approved + save the Publisher ID.
        if run.kind == "approval_flip":
            run.state = "running"
            s.add(run)
            s.commit()
            plan = json.loads(run.dry_run_plan or "{}")
            site = s.exec(select(Site).where(Site.domain == run.site_domain)).first()
            app = s.exec(select(NetworkApplication).where(
                NetworkApplication.site_id == site.id,
                func.lower(NetworkApplication.network_name) == (run.network_name or "").lower(),
            )).first()
            if app:
                app.status = ApplicationStatus.approved
                app.publisher_id = plan.get("publisher_id")
                app.response_date = date.today()
                s.add(app)
            run.result = json.dumps({"approved": True, "publisher_id": plan.get("publisher_id")})
            run.state = "done"
            s.add(run)
            s.add(AuditLog(actor=approver, actor_kind="human", action="approval.confirmed",
                           target=f"{run.site_domain}:{run.network_name}",
                           detail=json.dumps({"publisher_id": plan.get("publisher_id")})))
            s.commit()
            return {"workflow_id": run.id, "state": "done", "approved": True,
                    "publisher_id": plan.get("publisher_id")}

        return {"error": f"run kind '{run.kind}' has no approve handler"}


def approve_prepared(run_id: int, approver: str) -> dict:
    """Gate-only approval for reconcile-pipeline runs: RE-VALIDATE LIVE, and if it passes,
    mark the run 'approved' — but DO NOT execute (execute-from-answers is deferred)."""
    with Session(engine) as s:
        run = s.get(WorkflowRun, run_id)
        if not run:
            return {"error": "workflow not found"}
        if run.state != "awaiting_approval":
            return {"error": f"workflow is '{run.state}', not awaiting_approval"}
        if run.operation:  # a prepared reconcile run — validate the SHEET (RunAnswer rows)
            from . import pipeline
            chk = pipeline.check_run_ready(run_id)
            if not chk.get("ready"):
                return {"error": "cannot approve — fill these first: "
                        + ", ".join(chk.get("blockers") or ["required data missing"])}
        run.state = "approved"
        s.add(run)
        s.add(AuditLog(actor=approver, actor_kind="human", action="apply.approved_gate",
                       target=f"{run.site_domain}:{run.network_name}",
                       detail=json.dumps({"operation": run.operation})))
        s.commit()
        return {"workflow_id": run.id, "state": "approved",
                "note": "gate passed — execute is deferred (not run yet)"}


def execute_run(run_id: int, actor: str, force_live: bool = False) -> dict:
    """Execute an approved prepared run by submitting the SHEET verbatim (WYSIWYG): the
    field->value map comes from the run's RunAnswer rows, NOT re-derived from Billing Profile.
    Dry-run unless force_live. Create -> signup page; update -> profile/settings page."""
    from . import executor, pipeline
    with Session(engine) as s:
        run = s.get(WorkflowRun, run_id)
        if not run:
            return {"error": "workflow not found"}
        # State gate: LIVE requires an explicit approval; terminal/in-flight runs are blocked.
        if run.state in ("executing", "running"):
            return {"error": "a run is already executing — wait for it to finish"}
        if run.state in ("done", "failed", "rejected", "unverified"):
            return {"error": f"run is '{run.state}' — prepare a fresh sheet to run again"}
        if force_live and run.state != "approved":
            return {"error": "approve the sheet before you Execute LIVE"}
        if run.state not in ("approved", "awaiting_approval"):
            return {"error": f"run is '{run.state}'"}
        operation = run.operation or "create"
        site = s.exec(select(Site).where(Site.domain == run.site_domain)).first()
        hc = site.holding_company if site else None
        # ACCOUNT LOCK: only one live execute at a time per holding-company × network, so two
        # runs can't fight over the same account (whichever saved last would win + confuse verify).
        if force_live:
            for o in s.exec(select(WorkflowRun).where(WorkflowRun.state == "executing")).all():
                if o.id == run_id or (o.network_name or "").lower() != (run.network_name or "").lower():
                    continue
                o_site = s.exec(select(Site).where(Site.domain == o.site_domain)).first()
                if (o_site.holding_company if o_site else None) == hc:
                    return {"error": f"run #{o.id} is already executing on this account "
                                     "— wait for it to finish before starting another"}

    chk = pipeline.check_run_ready(run_id)  # gate on the sheet
    if not chk.get("ready"):
        return {"error": "cannot execute — fill these first: " + ", ".join(chk["blockers"])}
    # Only submit fields that actually differ from live (update) — don't re-type matching values.
    fields = pipeline.fields_to_submit(run_id)
    if not fields:
        with Session(engine) as s:
            run = s.get(WorkflowRun, run_id)
            run.state = "done"
            run.result = json.dumps({"mode": "NOOP", "note": "nothing to change — all fields already match the network"})
            s.add(run); s.commit()
        return {"workflow_id": run_id, "mode": "NOOP",
                "note": "nothing to change — the account already matches"}

    # Route to the best executor: deterministic script (head networks) or Skyvern (tail).
    result = executor.execute(operation, run.site_domain, run.network_name, fields, hc,
                              force_live=force_live)
    eng = result.get("engine")
    live = result.get("mode") == "LIVE"

    with Session(engine) as s:
        run = s.get(WorkflowRun, run_id)
        run.result = json.dumps(result)
        if eng == "script" and live:
            # Deterministic path is SYNCHRONOUS and already verified (it reloaded + read back).
            run.state = "done" if result.get("fully_verified") else "unverified"
        elif live:
            run.state = "executing"   # Skyvern is async — finalize_execute confirms it later
        else:
            run.state = "approved"    # dry-run
        s.add(run)
        s.add(AuditLog(actor=actor, actor_kind="human" if force_live else "agent",
                       action=("apply.executed" if force_live else "apply.execute_dryrun"),
                       target=f"{run.site_domain}:{run.network_name}",
                       detail=json.dumps({"engine": eng, "mode": result.get("mode"),
                                          "verified": result.get("verified")})))
        s.commit()

    # Deterministic path already verified against reality → converge the confirmed fields now.
    if eng == "script" and live:
        verified_fields = {k: fields[k] for k in (result.get("verified") or []) if k in fields}
        if verified_fields:
            pipeline.write_back(run_id, verified_fields, actor)
        return {"workflow_id": run_id, "operation": operation, "mode": "LIVE", "engine": "script",
                "verified": result.get("verified"), "unverified": result.get("unverified"),
                "seconds": result.get("seconds"), "result": result}

    return {"workflow_id": run_id, "operation": operation, "mode": result.get("mode"),
            "result": result}


def finalize_execute(run_id: int, actor: str = "system") -> dict:
    """Poll the live Skyvern run to terminal; ONLY on success, write the submitted values back
    to our records (network mirror + Billing Profile) so everything converges. On failure/partial,
    nothing is written back — the error is recorded on the run."""
    import httpx

    from . import pipeline
    from ..config import SKYVERN_API_KEY, SKYVERN_BASE_URL
    with Session(engine) as s:
        run = s.get(WorkflowRun, run_id)
        if not run:
            return {"error": "workflow not found"}
        result = json.loads(run.result or "{}")
        operation = run.operation or "create"
        network_name = run.network_name
        site = s.exec(select(Site).where(Site.domain == run.site_domain)).first()
        holding_company = site.holding_company if site else None
    rid = result.get("run_id")
    if not rid:
        return {"error": "no Skyvern run_id — this run wasn't executed live"}

    try:
        with httpx.Client(timeout=30) as c:
            t = c.get(f"{SKYVERN_BASE_URL.rstrip('/')}/api/v1/tasks/{rid}",
                      headers={"x-api-key": SKYVERN_API_KEY}).json()
    except Exception as exc:  # noqa: BLE001
        return {"error": f"poll failed: {type(exc).__name__}: {exc}"}
    status = t.get("status")

    if status != "completed":
        with Session(engine) as s:
            run = s.get(WorkflowRun, run_id)
            result["status"] = status
            result["failure_reason"] = t.get("failure_reason")
            run.result = json.dumps(result)
            if status in ("failed", "terminated", "canceled"):
                run.state = "failed"
            s.add(run)
            s.add(AuditLog(actor=actor, actor_kind="system", action="apply.execute_failed",
                           target=f"{run.site_domain}:{run.network_name}",
                           detail=json.dumps({"status": status})))
            s.commit()
        return {"run_id": rid, "status": status, "written_back": False}

    submitted = pipeline.fields_to_submit(run_id)

    # GUARDRAIL 1 — did the agent actually CLICK Save/Submit? Read Skyvern's own action log
    # (not the agent's self-report). No save click => typed but never submitted => NOT verified.
    save_clicked = None
    try:
        with httpx.Client(timeout=15) as c:
            acts = c.get(f"{SKYVERN_BASE_URL.rstrip('/')}/api/v1/tasks/{rid}/actions",
                         headers={"x-api-key": SKYVERN_API_KEY}).json()
        save_clicked = False
        for a in (acts or []):
            if a.get("action_type") == "click":
                rea = (a.get("reasoning") or "").lower()
                if any(k in rea for k in ("save", "submit", "update profile", "apply chang", "save chang", "confirm")):
                    save_clicked = True
                    break
    except Exception:  # noqa: BLE001
        save_clicked = None  # couldn't check — fall through to the read-back diff
    if save_clicked is False:
        with Session(engine) as s:
            run = s.get(WorkflowRun, run_id)
            result["status"] = status
            result["verified"] = []
            result["unverified"] = sorted(submitted.keys())
            result["unverified_reason"] = "no Save/Submit click found in the action log — values were typed but never submitted"
            run.result = json.dumps(result)
            run.state = "unverified"
            s.add(run)
            s.add(AuditLog(actor=actor, actor_kind="system", action="apply.unverified",
                           target=f"{run.site_domain}:{run.network_name}",
                           detail=json.dumps({"reason": "no save click"})))
            s.commit()
        return {"run_id": rid, "status": "unverified", "written_back": False,
                "reason": "Submit was never clicked"}

    def _norm(x):
        return str(x if x is not None else "").strip().lower()

    # GUARDRAIL 2 — AUTHORITATIVE VERIFY: independently read the LIVE account ourselves via a
    # deterministic script-reader (executor-agnostic — it verifies a Skyvern write just the same).
    # A plain browser reloads + reads the real persisted value; it never lies, unlike the agent's
    # self-report. If we have no script-reader for this network, fall back to the agent's read-back.
    from . import executor
    saved, verify_source = None, None
    try:
        saved = executor.verify_read(network_name, holding_company, list(submitted.keys()))
    except Exception:  # noqa: BLE001
        saved = None
    if saved is not None:
        verify_source = "independent-read"
    else:
        # Fallback — the agent's post-save read-back (weaker; can be fooled if it didn't reload).
        saved = {}
        ei = t.get("extracted_information") or {}
        if isinstance(ei, list):
            ei = ei[0] if (ei and isinstance(ei[0], dict)) else {}
        for it in (ei.get("saved_fields") or []):
            if isinstance(it, dict) and it.get("key"):
                saved[it["key"]] = it.get("persisted_value")
        verify_source = "agent-readback"

    verified = {k: v for k, v in submitted.items() if k in saved and _norm(saved[k]) == _norm(v)}
    unverified = {k: v for k, v in submitted.items() if k not in verified}

    # Converge our records ONLY for fields we actually confirmed persisted.
    wb = pipeline.write_back(run_id, verified, actor)

    # Fully verified only if we read something back AND everything matched.
    fully = bool(saved) and not unverified
    final_state = "done" if fully else "unverified"
    with Session(engine) as s:
        run = s.get(WorkflowRun, run_id)
        result["status"] = status
        result["verified"] = sorted(verified.keys())
        result["unverified"] = sorted(unverified.keys())
        result["read_back"] = saved
        result["verify_source"] = verify_source
        run.result = json.dumps(result)
        run.state = final_state
        if operation == "create" and fully:
            site = s.exec(select(Site).where(Site.domain == run.site_domain)).first()
            if site:
                app = s.exec(select(NetworkApplication).where(
                    NetworkApplication.site_id == site.id,
                    func.lower(NetworkApplication.network_name) == (run.network_name or "").lower(),
                )).first()
                if not app:
                    app = NetworkApplication(site_id=site.id, network_name=run.network_name)
                app.status = ApplicationStatus.applied
                app.submission_date = date.today()
                s.add(app)
        s.add(run)
        s.add(AuditLog(actor=actor, actor_kind="system",
                       action="apply.verified" if fully else "apply.unverified",
                       target=f"{run.site_domain}:{run.network_name}",
                       detail=json.dumps({"verified": sorted(verified), "unverified": sorted(unverified)})))
        s.commit()
    return {"run_id": rid, "status": final_state, "verified": sorted(verified.keys()),
            "unverified": sorted(unverified.keys()), "written_back": bool(verified)}


def reject_run(run_id: int, actor: str, reason: str = "") -> dict:
    with Session(engine) as s:
        run = s.get(WorkflowRun, run_id)
        if not run:
            return {"error": "workflow not found"}
        run.state = "rejected"
        s.add(run)
        s.add(AuditLog(
            actor=actor, actor_kind="human", action="apply.rejected",
            target=f"{run.site_domain}:{run.network_name}", detail=json.dumps({"reason": reason}),
        ))
        s.commit()
        return {"workflow_id": run.id, "state": "rejected"}


def list_runs(state: str | None = None) -> dict:
    with Session(engine) as s:
        q = select(WorkflowRun).order_by(WorkflowRun.created_at.desc())
        if state:
            q = q.where(WorkflowRun.state == state)
        runs = s.exec(q).all()
        return {"count": len(runs), "runs": [
            {
                "id": r.id, "site": r.site_domain, "network": r.network_name,
                "kind": r.kind, "state": r.state, "created_by": r.created_by,
                "plan": json.loads(r.dry_run_plan) if r.dry_run_plan else None,
            } for r in runs
        ]}


def _infer_network(text, names):
    t = (text or "").lower()
    for n in names:
        if n.lower() in t:
            return n
    return None


def propose_approval_flips(created_by: str = "inbox-parser") -> dict:
    """Scan the inbox; for each detected approval, propose a GATED status-flip:
    approval email -> mark the matching applied/awaiting application 'approved' + save Publisher ID.
    A human approves the flip in the console (never auto-flipped on an email alone)."""
    from .parser import scan_inbox
    scan = scan_inbox(20)
    if "error" in scan:
        return scan
    proposals = []
    with Session(engine) as s:
        names = [n.name for n in s.exec(select(Network)).all()]
        for appr in scan.get("approvals", []):
            network = _infer_network(f"{appr.get('subject','')} {appr.get('from','')}", names)
            if not network:
                continue
            pub = appr.get("publisher_id")
            apps = s.exec(select(NetworkApplication).where(
                func.lower(NetworkApplication.network_name) == network.lower())).all()
            for app in apps:
                if app.status.value not in ("applied", "awaiting"):
                    continue
                site = s.get(Site, app.site_id)
                if not site:
                    continue
                dup = s.exec(select(WorkflowRun).where(
                    WorkflowRun.site_domain == site.domain,
                    func.lower(WorkflowRun.network_name) == network.lower(),
                    WorkflowRun.kind == "approval_flip",
                    WorkflowRun.state == "awaiting_approval")).first()
                if dup:
                    continue
                plan = {"kind": "approval_flip", "site": site.domain, "network": network,
                        "publisher_id": pub, "from_status": app.status.value,
                        "email_subject": appr.get("subject"), "email_from": appr.get("from")}
                s.add(WorkflowRun(site_domain=site.domain, network_name=network, kind="approval_flip",
                                  state="awaiting_approval", dry_run_plan=json.dumps(plan), created_by=created_by))
                s.add(AuditLog(actor=created_by, actor_kind="agent", action="approval.detected",
                               target=f"{site.domain}:{network}", detail=json.dumps({"publisher_id": pub})))
                proposals.append({"site": site.domain, "network": network, "publisher_id": pub})
        s.commit()
    return {"detected": len(scan.get("approvals", [])), "proposals": proposals}
