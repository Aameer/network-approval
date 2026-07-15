"""Audit log read endpoint — every act crosses the policy boundary into here."""
from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..db import get_session
from ..models import AuditLog

router = APIRouter(prefix="/api", tags=["audit"])


@router.get("/audit")
def audit(limit: int = 50, session: Session = Depends(get_session)):
    rows = session.exec(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    ).all()
    return {"count": len(rows), "entries": rows}
