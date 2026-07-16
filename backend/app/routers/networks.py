"""Network registry — list, upsert (admin), and trigger discovery."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import Network
from ..services import discovery

router = APIRouter(prefix="/api/networks", tags=["networks"])


def _admin(request: Request) -> str:
    u = request.session.get("user")
    if not u:
        raise HTTPException(status_code=401, detail="sign in")
    if u.get("role") != "admin":
        raise HTTPException(status_code=403, detail="admin required")
    return u["email"]


@router.get("")
def list_networks(session: Session = Depends(get_session)):
    rows = session.exec(select(Network).order_by(Network.phase, Network.name)).all()
    return {"count": len(rows), "networks": [
        {"name": n.name, "phase": n.phase, "signup_url": n.signup_url,
         "login_url": n.login_url, "status": n.status} for n in rows
    ]}


class NetworkPatch(BaseModel):
    phase: Optional[int] = None
    signup_url: Optional[str] = None
    login_url: Optional[str] = None
    status: Optional[str] = None


@router.post("/{name}")
def upsert_network(name: str, patch: NetworkPatch, request: Request,
                   session: Session = Depends(get_session)):
    _admin(request)
    n = session.exec(select(Network).where(Network.name == name)).first()
    if not n:
        n = Network(name=name)
    for k, v in patch.model_dump(exclude_unset=True).items():
        setattr(n, k, v)
    session.add(n)
    session.commit()
    return {"name": name, "status": n.status, "signup_url": n.signup_url}


@router.post("/{name}/discover")
def discover(name: str, request: Request):
    _admin(request)
    return discovery.discover_signup_url(name)
