"""Secret read endpoints — ADMIN ONLY, audited. The whole sheet lives in C3; the
secret columns are queryable, but only by authorized (admin) callers."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..services import vault

router = APIRouter(prefix="/api", tags=["secrets"])


def _admin(request: Request) -> str:
    u = request.session.get("user")
    if not u:
        raise HTTPException(status_code=401, detail="sign in")
    if u.get("role") != "admin":
        raise HTTPException(status_code=403, detail="admin access required")
    return u["email"]


@router.get("/sites/{domain}/secrets")
def site_secrets(domain: str, request: Request):
    actor = _admin(request)
    r = vault.get_site_secrets(domain, actor)
    if "error" in r:
        raise HTTPException(status_code=404, detail=r["error"])
    return r


@router.get("/secrets/search")
def secrets_search(field: str, contains: str, request: Request):
    actor = _admin(request)
    return vault.find_sites_by_secret(field, contains, actor)


class SiteSecretIn(BaseModel):
    domain: str
    field: str
    value: str


@router.post("/site-secrets")
def store_site_secret(body: SiteSecretIn, request: Request):
    """Override a site secret value (admin only, audited). Value never returned."""
    actor = _admin(request)
    r = vault.store_site_secret(body.domain, body.field, body.value, actor)
    if "error" in r:
        raise HTTPException(status_code=400, detail=r["error"])
    return r


class NetCred(BaseModel):
    holding_company: str
    network: str
    username: str
    password: str


@router.post("/network-credentials")
def store_network_credential(body: NetCred, request: Request):
    """Store a network account login (encrypted). Admin only, audited."""
    actor = _admin(request)
    r = vault.store_network_credential(body.holding_company, body.network,
                                       body.username, body.password, actor)
    if "error" in r:
        raise HTTPException(status_code=400, detail=r["error"])
    return r
