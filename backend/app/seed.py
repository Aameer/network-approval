"""Seed the C3 registry from the portfolio inventory CSV.

Idempotent: if any Site rows exist, it does nothing. Run:  python -m app.seed
"""
import csv
import json
import os

from sqlmodel import Session, select

from .db import engine, init_db
from .models import ApplicationStatus, AuditLog, NetworkApplication, Site

_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
# Prefer the real (git-ignored) inventory; fall back to the committed sanitized sample.
DATA = os.path.join(_DIR, "portfolio_seed.csv")
if not os.path.exists(DATA):
    DATA = os.path.join(_DIR, "portfolio_seed.sample.csv")

SANDBOX = {"dailyreviewtoday.com", "saversheaven.com", "dailyessentialstips.com"}

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
                site = Site(
                    domain=domain,
                    holding_company=hc or None,
                    site_category=_clean(row.get("site_category")) or None,
                    website_status=_clean(row.get("website_status")) or None,
                    repo=_clean(row.get("repo_name")) or None,
                    vercel_project=_clean(row.get("vercel_project_name")) or None,
                    ga4_property_id=_clean(row.get("ga4_property_id")) or None,
                    is_sandbox=domain in SANDBOX,
                    phase=1 if domain in SANDBOX else 0,
                    notes=_clean(row.get("_notes")) or None,
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
                count += 1

        s.add(AuditLog(
            actor="system", actor_kind="system", action="seed_registry",
            target="portfolio", detail=json.dumps({"sites": count}),
        ))
        s.commit()
        print(f"seeded {count} sites ({len(SANDBOX)} sandbox with network state)")


if __name__ == "__main__":
    run()
