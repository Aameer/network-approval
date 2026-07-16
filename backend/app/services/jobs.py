"""Background jobs — the automation that runs without a human poking it.

- follow-up sweeper: applications past their next_followup_date still open -> alert
- milestone monitor: sandbox sites hitting 5k+/mo sessions -> Phase-2-ready alert

Alerts are written to the AuditLog (actor_kind='system') so they surface in the
console's Audit panel. A manual trigger endpoint runs both on demand for demos.
Scheduling uses APScheduler in-process (PoC); production would use Celery/beat.
"""
from __future__ import annotations

import json
from datetime import date

from sqlmodel import Session, select

from ..db import engine
from ..models import AuditLog, NetworkApplication, Site


def followup_sweeper() -> int:
    today = date.today()
    n = 0
    with Session(engine) as s:
        apps = s.exec(select(NetworkApplication).where(
            NetworkApplication.next_followup_date != None  # noqa: E711
        )).all()
        for a in apps:
            if a.next_followup_date and a.next_followup_date <= today and a.status.value in ("applied", "awaiting"):
                site = s.get(Site, a.site_id)
                s.add(AuditLog(actor="followup-monitor", actor_kind="system",
                               action="alert.followup_due",
                               target=f"{site.domain if site else a.site_id}:{a.network_name}",
                               detail=json.dumps({"due": a.next_followup_date.isoformat(), "status": a.status.value})))
                n += 1
        s.commit()
    return n


def milestone_monitor() -> int:
    from .traffic import get_traffic  # lazy (avoids importing BQ at module load)

    n = 0
    with Session(engine) as s:
        sites = s.exec(select(Site).where(Site.is_sandbox == True)).all()  # noqa: E712
        for site in sites:
            t = get_traffic(site.domain)
            sessions = t.get("sessions_30d")
            if sessions and sessions >= 5000 and site.phase < 2:
                s.add(AuditLog(actor="milestone-monitor", actor_kind="system",
                               action="alert.phase2_ready", target=site.domain,
                               detail=json.dumps({"sessions_30d": sessions})))
                n += 1
        s.commit()
    return n


def run_all() -> dict:
    return {"followups_alerted": followup_sweeper(), "milestones_alerted": milestone_monitor()}


def start_scheduler():
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except Exception:
        return None
    sched = BackgroundScheduler(daemon=True)
    sched.add_job(followup_sweeper, "interval", hours=6, id="followup", replace_existing=True)
    sched.add_job(milestone_monitor, "interval", hours=6, id="milestone", replace_existing=True)
    sched.start()
    return sched
