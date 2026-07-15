"""Registry writes — edit a site / override an application status.

C3 is the system of record, so edits happen here (not the sheet). Every write is an
ACT: it requires an authenticated user (identity gate) and records an AuditLog entry
with the old->new diff. Read/write RBAC (row + column scopes) is a documented
production step; the PoC is single-role, see-and-edit-everything.
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import engine
from ..models import ApplicationStatus, AuditLog, NetworkApplication, Site

router = APIRouter(prefix="/api", tags=["registry-write"])


def _user(request: Request) -> str:
    u = request.session.get("user")
    if not u:
        raise HTTPException(status_code=401, detail="sign in to edit")
    return u["email"]


class SitePatch(BaseModel):
    holding_company: Optional[str] = None
    site_category: Optional[str] = None
    website_status: Optional[str] = None
    website_type: Optional[str] = None
    country: Optional[str] = None
    redirection_status: Optional[str] = None
    phase: Optional[int] = None
    notes: Optional[str] = None


@router.patch("/sites/{domain}")
def edit_site(domain: str, patch: SitePatch, request: Request):
    editor = _user(request)
    with Session(engine) as s:
        site = s.exec(select(Site).where(Site.domain == domain)).first()
        if not site:
            raise HTTPException(status_code=404, detail="site not found")
        changes = {}
        for field, val in patch.model_dump(exclude_unset=True).items():
            old = getattr(site, field)
            if old != val:
                setattr(site, field, val)
                changes[field] = {"from": old, "to": val}
        if changes:
            s.add(site)
            s.add(AuditLog(actor=editor, actor_kind="human", action="site.edit",
                           target=domain, detail=json.dumps(changes)))
            s.commit()
        return {"domain": domain, "changes": changes}


class AppPatch(BaseModel):
    status: Optional[str] = None
    publisher_id: Optional[str] = None
    rejection_reason: Optional[str] = None


@router.patch("/applications/{app_id}")
def override_application(app_id: int, patch: AppPatch, request: Request):
    editor = _user(request)
    with Session(engine) as s:
        app = s.get(NetworkApplication, app_id)
        if not app:
            raise HTTPException(status_code=404, detail="application not found")
        changes = {}
        data = patch.model_dump(exclude_unset=True)
        if data.get("status"):
            try:
                newst = ApplicationStatus(data["status"])
            except ValueError:
                raise HTTPException(status_code=400, detail=f"invalid status '{data['status']}'")
            if app.status != newst:
                changes["status"] = {"from": app.status.value, "to": newst.value}
                app.status = newst
        for f in ("publisher_id", "rejection_reason"):
            if f in data and getattr(app, f) != data[f]:
                changes[f] = {"from": getattr(app, f), "to": data[f]}
                setattr(app, f, data[f])
        if changes:
            s.add(app)
            s.add(AuditLog(actor=editor, actor_kind="human", action="application.override",
                           target=f"app:{app_id}", detail=json.dumps(changes)))
            s.commit()
        return {"application_id": app_id, "changes": changes}
