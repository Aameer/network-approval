"""Inbox parser endpoint — reads the holding-co mailbox (auth required)."""
from fastapi import APIRouter, HTTPException, Request

from ..services import parser

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


@router.post("/scan")
def scan(request: Request, limit: int = 15):
    if not request.session.get("user"):
        raise HTTPException(status_code=401, detail="sign in")
    return parser.scan_inbox(limit)


@router.post("/detect-approvals")
def detect_approvals(request: Request):
    """Scan inbox + propose gated status-flips for detected approvals."""
    if not request.session.get("user"):
        raise HTTPException(status_code=401, detail="sign in")
    from ..services import apply
    return apply.propose_approval_flips()
