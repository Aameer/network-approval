"""The copilot's tool belt. PoC = read-only tools (run free, no gate).

Act tools (apply_to_network, set_status) land next — they'll return a dry-run and
require approval before executing, and every act writes an AuditLog entry.
"""
from __future__ import annotations

from sqlmodel import Session, select

from ..db import engine
from ..models import NetworkApplication, Site
from . import gcms, vault
from .apply import create_apply_run


def read_portfolio(sandbox_only: bool = False, holding_company: str | None = None) -> dict:
    """List sites in the registry with their per-network application status."""
    with Session(engine) as s:
        sites = s.exec(select(Site)).all()
        out = []
        for site in sites:
            if sandbox_only and not site.is_sandbox:
                continue
            if holding_company and holding_company.lower() not in (site.holding_company or "").lower():
                continue
            apps = s.exec(
                select(NetworkApplication).where(NetworkApplication.site_id == site.id)
            ).all()
            out.append({
                "domain": site.domain,
                "holding_company": site.holding_company,
                "phase": site.phase,
                "is_sandbox": site.is_sandbox,
                "networks": [
                    {"network": a.network_name, "status": a.status.value, "publisher_id": a.publisher_id}
                    for a in apps
                ],
            })
        return {"count": len(out), "sites": out}


def get_site(domain: str) -> dict:
    """Live site truth from GCMS (pages/entity/tags). Degrades gracefully if GCMS creds unset."""
    return gcms.get_site(domain)


def get_traffic(domain: str) -> dict:
    """Traffic for a site. STUBBED in the PoC — wires to ads-ops-hub / BigQuery facts_performance."""
    return {
        "domain": domain,
        "source": "stub",
        "sessions_30d": None,
        "note": "traffic read is stubbed for the PoC; production reads facts_performance in BigQuery",
    }


def apply_to_network(domain: str, network: str) -> dict:
    """PROPOSE applying a site to a network. Creates a GATED dry-run for human approval — does NOT submit."""
    return create_apply_run(domain, network, created_by="copilot")


# --- Anthropic tool schemas ---
TOOLS = [
    {
        "name": "read_portfolio",
        "description": "List sites in the C3 registry with per-affiliate-network application status "
                       "(not_applied/applied/awaiting/approved/rejected). Use for portfolio questions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sandbox_only": {"type": "boolean", "description": "Only the 3 sandbox sites."},
                "holding_company": {"type": "string", "description": "Filter by holding company / MCC (substring)."},
            },
            "required": [],
        },
    },
    {
        "name": "get_site",
        "description": "Fetch live site truth (name, entity, tags, regions) from GCMS by domain.",
        "input_schema": {
            "type": "object",
            "properties": {"domain": {"type": "string", "description": "e.g. dailyreviewtoday.com"}},
            "required": ["domain"],
        },
    },
    {
        "name": "get_traffic",
        "description": "Get traffic (sessions) for a site. Currently stubbed in the PoC.",
        "input_schema": {
            "type": "object",
            "properties": {"domain": {"type": "string"}},
            "required": ["domain"],
        },
    },
    {
        "name": "apply_to_network",
        "description": "PROPOSE applying a site to an affiliate network. Creates a gated dry-run "
                       "(the application plan) that a human must approve in the console. Does NOT "
                       "submit and cannot self-approve. Returns the plan + workflow_id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "e.g. dailyreviewtoday.com"},
                "network": {"type": "string", "description": "e.g. SourceKnowledge"},
            },
            "required": ["domain", "network"],
        },
    },
]

DISPATCH = {
    "read_portfolio": read_portfolio,
    "get_site": get_site,
    "get_traffic": get_traffic,
    "apply_to_network": apply_to_network,
}

# --- ADMIN-ONLY secret tools (added to the copilot's belt only when the user is admin) ---
SECRET_TOOLS = [
    {
        "name": "get_site_secrets",
        "description": "ADMIN ONLY. Return the decrypted secrets (MCC admin password, payment "
                       "card, payment link) for one site. Audited on every access.",
        "input_schema": {
            "type": "object",
            "properties": {"domain": {"type": "string"}},
            "required": ["domain"],
        },
    },
    {
        "name": "find_sites_by_secret",
        "description": "ADMIN ONLY. Find sites whose secret field contains a value — e.g. which "
                       "sites use a payment card ending 8435 (field=payment_profile_card, "
                       "contains='8435'). Audited.",
        "input_schema": {
            "type": "object",
            "properties": {
                "field": {"type": "string", "enum": vault.SECRET_FIELDS},
                "contains": {"type": "string"},
            },
            "required": ["field", "contains"],
        },
    },
]
SECRET_DISPATCH = {
    "get_site_secrets": vault.get_site_secrets,
    "find_sites_by_secret": vault.find_sites_by_secret,
}
SECRET_TOOL_NAMES = set(SECRET_DISPATCH)
