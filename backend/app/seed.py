"""Seed the C3 registry from the portfolio inventory CSV.

Idempotent: if any Site rows exist, it does nothing. Run:  python -m app.seed
"""
import csv
import json
import os

from sqlmodel import Session, select

from .db import engine, init_db
from .models import ApplicationStatus, AuditLog, NetworkApplication, Site, SiteSecret
from .services import vault

_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
# Prefer the real (git-ignored) inventory; fall back to the committed sanitized sample.
DATA = os.path.join(_DIR, "portfolio_seed.csv")
if not os.path.exists(DATA):
    DATA = os.path.join(_DIR, "portfolio_seed.sample.csv")

SANDBOX = {"dailyreviewtoday.com", "saversheaven.com", "dailyessentialstips.com"}

# Never store these in the C3 DB.
SENSITIVE = {"mcc_admin_password", "payment_profile_card", "payment_profile_link"}

# Correct GA4 property ids (from the dg GA4 inventory) — the portfolio sheet leaves these blank.
SANDBOX_GA4 = {"dailyreviewtoday.com": "524894814", "saversheaven.com": "526496223"}

# Known network state for the sandbox trio (from the playbook) so the demo dashboard is real.
SANDBOX_APPS = {
    "dailyreviewtoday.com": {
        "YieldKit": "approved", "ChineseAn": "approved", "Admitad": "awaiting",
        "SourceKnowledge": "not_applied", "BrandReward": "not_applied",
    },
    "saversheaven.com": {
        "YieldKit": "approved", "SourceKnowledge": "not_applied",
        "ChineseAn": "not_applied", "BrandReward": "not_applied",
    },
    "dailyessentialstips.com": {
        "YieldKit": "approved", "SourceKnowledge": "not_applied",
        "ChineseAn": "not_applied", "BrandReward": "not_applied",
    },
}


def _clean(v):
    v = (v or "").strip()
    return "" if v.upper() in ("NOT ACTIVE", "_GAP") else v


def run():
    init_db()
    with Session(engine) as s:
        if s.exec(select(Site)).first():
            print("registry already seeded — skipping")
            return

        count = 0
        with open(DATA, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                domain = _clean(row.get("domain"))
                if not domain:
                    continue
                hc = _clean(row.get("mcc_name")) or _clean(row.get("account_name"))
                g = lambda col: _clean(row.get(col)) or None  # noqa: E731
                raw = {k: v for k, v in row.items() if k not in SENSITIVE and _clean(v)}
                site = Site(
                    domain=domain,
                    holding_company=hc or None,
                    site_category=g("site_category"),
                    website_status=g("website_status"),
                    repo=g("repo_name"),
                    repo_link=g("repo_link"),
                    repo_criticality=g("repo_criticality"),
                    repo_status=g("repo_status"),
                    vercel_project=g("vercel_project_name"),
                    ga4_property_id=SANDBOX_GA4.get(domain) or g("ga4_property_id"),
                    persona=g("Persona"),
                    country=g("country"),
                    mcc_id=g("mcc_id"),
                    mcc_admin_email=g("mcc_admin_email"),
                    website_type=g("website_type"),
                    redirection_status=g("redirection_status"),
                    clickout_moved=g("clickout_moved"),
                    wct_user_website_id=g("wct_user_website_id"),
                    gtm_tag=g("gtm_tag"),
                    registered_on=g("registered_on"),
                    domain_expiry=g("domain_expiry"),
                    privacy_protection=g("privacy_protection"),
                    is_sandbox=domain in SANDBOX,
                    phase=1 if domain in SANDBOX else 0,
                    notes=g("_notes"),
                    raw=json.dumps(raw, ensure_ascii=False),
                )
                s.add(site)
                s.flush()  # assign site.id

                for net, st in SANDBOX_APPS.get(domain, {}).items():
                    s.add(NetworkApplication(
                        site_id=site.id,
                        network_name=net,
                        status=ApplicationStatus(st),
                        publisher_id=(f"PUB-{1000 + site.id}" if st == "approved" else None),
                    ))
                # store the sheet's secret columns encrypted (never plaintext)
                if vault.enabled():
                    for sf in vault.SECRET_FIELDS:
                        val = _clean(row.get(sf))
                        if val:
                            s.add(SiteSecret(site_id=site.id, field=sf, value_enc=vault.encrypt(val)))
                count += 1

        s.add(AuditLog(
            actor="system", actor_kind="system", action="seed_registry",
            target="portfolio", detail=json.dumps({"sites": count}),
        ))
        s.commit()
        print(f"seeded {count} sites ({len(SANDBOX)} sandbox with network state)")


if __name__ == "__main__":
    run()
