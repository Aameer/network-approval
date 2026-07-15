"""Auth — PoC stub. Real Google OIDC wires in where noted (reuse 8thloop GCP project).

The identity gate: every actor (human or agent) is named + scoped. For the PoC we
seed a session user; swapping in Google login is a drop-in at `dev_login`.
"""
from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/me")
def me(request: Request):
    user = request.session.get("user")
    if user:
        return {"authenticated": True, "user": user}
    return {"authenticated": False}


@router.post("/dev-login")
def dev_login(request: Request, role: str = "admin"):
    # TODO: replace with Google OIDC callback — verify id_token, enforce ALLOWED_LOGIN_DOMAIN.
    # role defaults to admin for the demo; pass ?role=operator to test the non-admin gating.
    user = {"email": "aameer@8thloop.com", "name": "Aameer", "role": role}
    request.session["user"] = user
    return {"authenticated": True, "user": user, "note": "stub login — Google OIDC replaces this"}


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"authenticated": False}
