"""The act-gate: propose (dry-run) -> human approves -> agent executes -> audit.

The real network submission is STUBBED (_execute_apply). Swap it for the Skyvern/
browser agent (reuse coupon-engine's stack) once MUX SourceKnowledge creds land — the
gate, workflow, status update, and audit trail are all real already.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

from sqlalchemy import func
from sqlmodel import Session, select

from ..db import engine
from ..models import ApplicationStatus, AuditLog, NetworkApplication, Site, WorkflowRun
from . import vault

# Playbook Phase-0/1 application pack — what a real apply would attach.
_DOCS = [
    "incorporation doc", "W8-BEN / tax", "company + bank details",
    "GA4 screenshot (7+30d)", "GSC screenshot", "about brief (1000w)", "traffic brief (1000w)",
]


def build_dry_run(domain: str, network: str) -> dict:
    with Session(engine) as s:
        site = s.exec(select(Site).where(Site.domain == domain)).first()
        if not site:
            return {"error": f"unknown site {domain}"}
        return {
            "site": domain,
            "network": network,
            "holding_company": site.holding_company,
            "email": site.mcc_admin_email or "(holding-co inbox — from vault/config)",
            "documents": _DOCS,
            "form_answers": {
                "website_type": "Coupon / Deals / Shopping",
                "traffic_sources": "SEO, social, paid search, direct, content",
                "regions": "US, UK (+ per niche)",
                "disclosure": "read & accept (site has live Affiliate Disclosure)",
            },
            "captcha": "auto-solve via CAPSOLVER; else queue to human",
            "credentials_available": vault.has_network_credential(site.holding_company or "", network),
            "credentials_ref": (f"netcred:{site.holding_company}:{network}"
                                if vault.has_network_credential(site.holding_company or "", network) else None),
            "credentials": "leased at submit time from the encrypted store — never in this plan",
        }


def create_apply_run(domain: str, network: str, created_by: str = "copilot") -> dict:
    # Canonicalize the network name to an existing application (case-insensitive),
    # so "admitad" updates the seeded "Admitad" instead of creating a duplicate.
    with Session(engine) as s:
        site = s.exec(select(Site).where(Site.domain == domain)).first()
        if not site:
            return {"error": f"unknown site {domain}"}
        existing = s.exec(select(NetworkApplication).where(
            NetworkApplication.site_id == site.id,
            func.lower(NetworkApplication.network_name) == network.lower(),
        )).first()
        if existing:
            network = existing.network_name

    plan = build_dry_run(domain, network)
    if "error" in plan:
        return plan
    with Session(engine) as s:
        run = WorkflowRun(
            site_domain=domain, network_name=network, kind="apply",
            state="awaiting_approval", dry_run_plan=json.dumps(plan), created_by=created_by,
        )
        s.add(run)
        s.commit()
        s.refresh(run)
        s.add(AuditLog(
            actor=created_by, actor_kind="agent", action="apply.proposed",
            target=f"{domain}:{network}", detail=json.dumps({"workflow_id": run.id}),
        ))
        s.commit()
        return {"workflow_id": run.id, "state": run.state, "plan": plan,
                "note": "dry-run only — awaiting human approval in the console"}


def _execute_apply(run: WorkflowRun) -> dict:
    # Real apply via Skyvern remote browser (dry-runnable until SKYVERN_LIVE=true).
    from . import skyvern
    plan = json.loads(run.dry_run_plan) if run.dry_run_plan else {}
    return skyvern.submit_application(run.site_domain, run.network_name, plan,
                                      holding_company=plan.get("holding_company"))


def approve_run(run_id: int, approver: str) -> dict:
    with Session(engine) as s:
        run = s.get(WorkflowRun, run_id)
        if not run:
            return {"error": "workflow not found"}
        if run.state != "awaiting_approval":
            return {"error": f"workflow is '{run.state}', not awaiting_approval"}

        run.state = "running"
        s.add(run)
        s.commit()

        result = _execute_apply(run)

        site = s.exec(select(Site).where(Site.domain == run.site_domain)).first()
        app = s.exec(select(NetworkApplication).where(
            NetworkApplication.site_id == site.id,
            func.lower(NetworkApplication.network_name) == run.network_name.lower(),
        )).first()
        if not app:
            app = NetworkApplication(site_id=site.id, network_name=run.network_name)
        app.status = ApplicationStatus.applied
        app.submission_date = date.today()
        app.next_followup_date = date.today() + timedelta(days=14)
        s.add(app)

        run.state = "done"
        s.add(run)
        s.add(AuditLog(
            actor=approver, actor_kind="human", action="apply.approved",
            target=f"{run.site_domain}:{run.network_name}", detail=json.dumps(result),
        ))
        s.commit()
        return {"workflow_id": run.id, "state": "done", "applied": True, "result": result}


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
