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
from ..models import AuditLog, Site, SiteSecret

# Columns from the inventory sheet that are secrets, not open registry fields.
SECRET_FIELDS = ["mcc_admin_password", "payment_profile_card", "payment_profile_link"]

_f: Optional[Fernet] = Fernet(SECRETS_KEY.encode()) if SECRETS_KEY else None


def enabled() -> bool:
    return _f is not None


def encrypt(plain: str) -> str:
    return _f.encrypt(plain.encode()).decode()


def decrypt(token: str) -> str:
    return _f.decrypt(token.encode()).decode()


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
