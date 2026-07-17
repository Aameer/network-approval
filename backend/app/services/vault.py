"""Secret storage — the whole sheet lives in C3, but secret columns are treated as
secrets: encrypted at rest (Fernet), queryable ONLY by authorized (admin) callers,
and every access audited.

PoC uses a Fernet key from env (SECRETS_KEY). Production swaps this for a real KMS /
secrets manager — the encrypt/decrypt seam stays the same.
"""
from __future__ import annotations

import json
from typing import Optional

from cryptography.fernet import Fernet
from sqlmodel import Session, select

from ..config import SECRETS_KEY
from ..db import engine
from ..models import AuditLog, NetworkCredential, Site, SiteSecret

# Columns from the inventory sheet that are secrets, not open registry fields.
SECRET_FIELDS = ["mcc_admin_password", "payment_profile_card", "payment_profile_link"]

_f: Optional[Fernet] = Fernet(SECRETS_KEY.encode()) if SECRETS_KEY else None


def enabled() -> bool:
    return _f is not None


def encrypt(plain: str) -> str:
    return _f.encrypt(plain.encode()).decode()


def decrypt(token: str) -> str:
    return _f.decrypt(token.encode()).decode()


def store_site_secret(domain: str, field: str, value: str, actor: str = "admin") -> dict:
    """Override (set) a site secret value — encrypted, audited. Value is never returned."""
    if not enabled():
        return {"error": "secrets store not configured"}
    if field not in SECRET_FIELDS:
        return {"error": f"'{field}' is not a secret field"}
    with Session(engine) as s:
        site = s.exec(select(Site).where(Site.domain == domain)).first()
        if not site:
            return {"error": f"unknown site {domain}"}
        row = s.exec(select(SiteSecret).where(
            SiteSecret.site_id == site.id, SiteSecret.field == field)).first()
        if row:
            row.value_enc = encrypt(value)
        else:
            row = SiteSecret(site_id=site.id, field=field, value_enc=encrypt(value))
        s.add(row)
        s.add(AuditLog(actor=actor, actor_kind="human", action="secret.override",
                       target=f"{domain}:{field}", detail="{}"))
        s.commit()
        return {"domain": domain, "field": field, "stored": True}


def get_site_secrets(domain: str, actor: str = "admin") -> dict:
    """Decrypt + return a site's secrets. Caller MUST already be authorized (admin)."""
    if not enabled():
        return {"error": "secrets store not configured (SECRETS_KEY unset)"}
    with Session(engine) as s:
        site = s.exec(select(Site).where(Site.domain == domain)).first()
        if not site:
            return {"error": f"unknown site {domain}"}
        rows = s.exec(select(SiteSecret).where(SiteSecret.site_id == site.id)).all()
        out = {r.field: decrypt(r.value_enc) for r in rows}
        s.add(AuditLog(actor=actor, actor_kind="human", action="secret.viewed",
                       target=domain, detail=json.dumps({"fields": list(out)})))
        s.commit()
        return {"domain": domain, "secrets": out}


def find_sites_by_secret(field: str, contains: str, actor: str = "admin") -> dict:
    """Find sites whose secret `field` contains `contains` (e.g. a card's last-4).
    Caller MUST already be authorized (admin). Audited."""
    if not enabled():
        return {"error": "secrets store not configured"}
    if field not in SECRET_FIELDS:
        return {"error": f"'{field}' is not a secret field"}
    matches = []
    with Session(engine) as s:
        rows = s.exec(select(SiteSecret).where(SiteSecret.field == field)).all()
        for r in rows:
            try:
                val = decrypt(r.value_enc)
            except Exception:
                continue
            if contains.lower() in val.lower():
                site = s.get(Site, r.site_id)
                matches.append({"domain": site.domain if site else "?", "value": val})
        s.add(AuditLog(actor=actor, actor_kind="human", action="secret.search",
                       target=field, detail=json.dumps({"contains": contains, "hits": len(matches)})))
        s.commit()
    return {"field": field, "contains": contains, "count": len(matches), "matches": matches}


def sites_with_secrets() -> set[int]:
    if not enabled():
        return set()
    with Session(engine) as s:
        return set(s.exec(select(SiteSecret.site_id)).all())


# --- network account credentials (leased by the apply agent at runtime) ---

def _find_netcred(s, holding_company: str, network: str):
    hc, net = (holding_company or "").lower(), (network or "").lower()
    for c in s.exec(select(NetworkCredential)).all():
        if c.holding_company.lower() == hc and c.network.lower() == net:
            return c
    return None


def has_network_credential(holding_company: str, network: str) -> bool:
    if not enabled():
        return False
    with Session(engine) as s:
        return _find_netcred(s, holding_company, network) is not None


def network_credential_username(holding_company: str, network: str) -> Optional[str]:
    """The stored account email/username — NOT a secret (password stays encrypted),
    so it's safe to surface in a plan without auditing. None if no credential."""
    if not enabled():
        return None
    with Session(engine) as s:
        c = _find_netcred(s, holding_company, network)
        return c.username if c else None


def network_credential_password_ok(holding_company: str, network: str, rule: str = "alnum") -> bool:
    """Validity check WITHOUT exposing or auditing the value — True only if a credential
    exists and its password satisfies `rule` (alnum = alphanumeric, some networks require it)."""
    if not enabled():
        return False
    with Session(engine) as s:
        c = _find_netcred(s, holding_company, network)
        if not c:
            return False
        try:
            pw = decrypt(c.password_enc)
        except Exception:
            return False
        return pw.isalnum() if rule == "alnum" else bool(pw)


def store_network_credential(holding_company: str, network: str, username: str,
                             password: str, actor: str = "admin") -> dict:
    if not enabled():
        return {"error": "secrets store not configured (SECRETS_KEY unset)"}
    with Session(engine) as s:
        c = _find_netcred(s, holding_company, network)
        if c:
            c.username, c.password_enc = username, encrypt(password)
        else:
            c = NetworkCredential(holding_company=holding_company, network=network,
                                  username=username, password_enc=encrypt(password))
        s.add(c)
        s.add(AuditLog(actor=actor, actor_kind="human", action="credential.stored",
                       target=f"{holding_company}:{network}", detail="{}"))
        s.commit()
        return {"credentials_ref": f"netcred:{holding_company}:{network}", "stored": True}


def lease_network_credential(holding_company: str, network: str, actor: str = "apply-agent") -> dict:
    """Decrypt + return a network login for the apply agent. Audited on every lease."""
    if not enabled():
        return {"error": "secrets store not configured"}
    with Session(engine) as s:
        c = _find_netcred(s, holding_company, network)
        if not c:
            return {"error": f"no stored credential for {holding_company}:{network}"}
        s.add(AuditLog(actor=actor, actor_kind="agent", action="credential.leased",
                       target=f"{holding_company}:{network}", detail="{}"))
        s.commit()
        return {"username": c.username, "password": decrypt(c.password_enc)}
