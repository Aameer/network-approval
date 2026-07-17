"""Signup-URL discovery + form scouting.

Signup-URL discovery: web-search + official-domain guardrail (skeleton below).

Form scouting (scout_*): a READ-ONLY Skyvern run that logs into an existing account,
opens the profile/settings page, and maps every field (label/type/required/options/current
value) via data-extraction — never changing or submitting anything. The mapped fields are
saved as the network's 'profile' form schema, which the Prepare step then answers from our DB.
"""
from __future__ import annotations

import json
from datetime import datetime
from urllib.parse import urlparse


def official_domain_ok(network: str, url: str) -> bool:
    """Guardrail: the URL host must contain the network's name (never a look-alike site).
    Real impl would compare the registrable domain against a known-domains list."""
    if not url:
        return False
    host = (urlparse(url).hostname or "").lower().replace("-", "").replace(".", "")
    net = (network or "").lower().replace(" ", "").replace("-", "")
    return bool(net) and net in host


def discover_signup_url(network: str) -> dict:
    return {
        "network": network,
        "status": "pending",
        "plan": [
            f"web-search: '{network} affiliate publisher signup'",
            "fetch top candidates; confirm a self-serve publisher signup form (not a merchant page)",
            f"validate the URL is on {network}'s official registrable domain (official_domain_ok)",
            "cache to the Network registry — status=verified on domain-match, else pending human confirm",
        ],
        "guardrail": "a URL that fails official_domain_ok is NEVER accepted (anti-phishing)",
        "note": "skeleton — wire a search API (WebSearch/SerpAPI) + fetch/validate to auto-fill. "
                "The browser agent (Skyvern) handles the form fields at runtime, so only the "
                "validated entry URL needs to be discovered + cached.",
    }


# ---------------------------------------------------------------------------
# Form scouting — read-only mapping of a logged-in profile/settings page
# ---------------------------------------------------------------------------

# The shape we ask Skyvern to extract from the page.
_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "the field's visible label"},
                    "section": {"type": "string", "description": "which tab/section the field is on (Profile, Payments, etc.)"},
                    "type": {"type": "string", "description": "text|email|tel|url|select|checkbox|password|number"},
                    "required": {"type": "boolean"},
                    "options": {"type": "array", "items": {"type": "string"}, "description": "dropdown options if any"},
                    "current_value": {"type": "string", "description": "the value currently in the field"},
                    "rule": {"type": "string", "description": "validation/format constraint if any, e.g. 'must be a valid URL (with https)', 'alphanumeric only', 'digits only', 'min 8 chars'"},
                    "help": {"type": "string", "description": "placeholder or help text shown near the field"},
                },
            },
        }
    },
}

# Map a discovered label -> our canonical answer key (so Prepare can resolve it from the DB).
# Ordered: substring match, first hit wins. Specific/exact cases are handled in _label_to_key.
_LABEL_KEYS = [
    ("paypal", "paypal_email"), ("payout", "paypal_email"),
    ("company", "company_name"),
    ("billing name", "billing_name"), ("billing contact", "billing_name"),
    ("street", "address1"), ("address line 1", "address1"), ("address", "address1"),
    ("apartment", "address2"), ("suite", "address2"), ("address line 2", "address2"),
    ("city", "city"), ("town", "city"),
    ("state", "state"), ("province", "state"), ("region", "state"),
    ("zip", "zip_code"), ("postal", "zip_code"), ("postcode", "zip_code"),
    ("country", "country"),
    ("phone", "phone"), ("mobile", "phone"),
    ("confirm password", "password_confirm"), ("password", "password"),
    ("tax", "tax_id"), ("vat", "tax_id"),
    ("website", "website_url"), ("url", "website_url"),
]

# Labels that are exactly the account email (never a notification/report checkbox).
_EMAIL_EXACT = {"email", "e-mail", "email address", "account email", "login email"}
_NAME_EXACT = {"name", "full name", "contact name", "contact person name"}


def _label_to_key(label: str) -> str:
    lo = (label or "").lower().strip()
    if lo in _EMAIL_EXACT:
        return "email"
    if "first name" in lo:
        return "first_name"
    if "last name" in lo:
        return "last_name"
    if lo in _NAME_EXACT:
        return "contact_name"
    for needle, key in _LABEL_KEYS:
        if needle in lo:
            return key
    return "unmapped:" + lo.replace(" ", "_")[:30]


def _to_schema(extracted: dict) -> dict:
    """Convert Skyvern's extracted field list into our stored form-schema shape."""
    fields = []
    for f in (extracted or {}).get("fields", []):
        label = f.get("label") or ""
        fields.append({
            "key": _label_to_key(label),
            "label": label,
            "section": f.get("section"),
            "type": f.get("type"),
            "required": bool(f.get("required")),
            "options": f.get("options") or None,
            "current_value": f.get("current_value"),
            "rule": f.get("rule"),
            "help": f.get("help"),
        })
    return {"pages": [{"page": 1, "fields": fields}]}


def _entry_url(network: str):
    from sqlmodel import Session, select
    from ..db import engine
    from ..models import Network
    with Session(engine) as s:
        n = next((r for r in s.exec(select(Network)).all()
                  if r.name.lower() == (network or "").lower()), None)
        if not n:
            return None
        return n.profile_url or n.login_url  # log in, then find settings


def build_scout_task(network: str, entry_url: str) -> dict:
    """The read-only scout task (credentials injected at submit, never stored)."""
    return {
        "url": entry_url,
        "navigation_goal": (
            "Log in using credentials.username and credentials.password. Then map the account's "
            "editable fields across its settings tabs, working METHODICALLY and EFFICIENTLY: open "
            "each tab/section EXACTLY ONCE (Profile/Account, Billing, Payments/Payout, Notifications, "
            "and any others) and read its fields before moving on. Do NOT revisit a tab you've "
            "already opened, and do NOT click the same navigation items repeatedly — that wastes "
            "steps. Give priority to the Billing/Payments/Payout section (payout method, PayPal "
            "email, bank details). If a field reveals more fields when a value is picked (e.g. "
            "payout method → PayPal vs bank), note the branch. STRICTLY READ-ONLY, NO REAL DETAILS: "
            "enter nothing but the login. If a tab is locked because the account is 'under review', "
            "record that it exists but is not yet accessible, and move on."
        ),
        "data_extraction_goal": (
            "List EVERY editable field found across ALL settings tabs (profile, payments/payout, "
            "billing, notifications, etc.). For each field capture: its visible label, which "
            "tab/section it is on, its input type (text/email/tel/url/select/checkbox/number), "
            "whether it is required, its dropdown options if it is a select, its current value, any "
            "VALIDATION/FORMAT rule (e.g. 'must be a valid URL with https', 'alphanumeric only', "
            "'digits only', min length), and any placeholder/help text shown near it. Include the "
            "payout/PayPal field(s) even if the account is under review."
        ),
        "extracted_information_schema": _EXTRACT_SCHEMA,
        "navigation_payload": {},   # credentials added at submit
        "proxy_location": "RESIDENTIAL",
        "max_steps_per_run": 25,    # walking every tab + extracting needs more than the default ~10
    }


def submit_scout(domain: str, network: str, created_by: str = "scout") -> dict:
    """Fire a read-only profile scout. Returns the Skyvern run_id + our workflow id."""
    from sqlmodel import Session, select
    from ..config import SKYVERN_API_KEY, SKYVERN_BASE_URL
    from ..db import engine
    from ..models import AuditLog, Site, WorkflowRun
    from . import vault

    entry = _entry_url(network)
    if not entry:
        return {"error": f"no login/profile URL for {network} — set it in the Network registry"}
    with Session(engine) as s:
        site = s.exec(select(Site).where(Site.domain == domain)).first()
        if not site:
            return {"error": f"unknown site {domain}"}
        hc = site.holding_company or ""

    leased = vault.lease_network_credential(hc, network)
    if "error" in leased:
        return {"error": leased["error"] + " — store the account login first"}

    task = build_scout_task(network, entry)
    task["navigation_payload"]["credentials"] = {"username": leased["username"], "password": leased["password"]}

    if not (SKYVERN_API_KEY and SKYVERN_BASE_URL):
        return {"error": "Skyvern not configured"}
    try:
        import httpx
        headers = {"x-api-key": SKYVERN_API_KEY, "Content-Type": "application/json"}
        with httpx.Client(timeout=60) as c:
            r = c.post(f"{SKYVERN_BASE_URL.rstrip('/')}/api/v1/tasks", headers=headers, json=task)
            r.raise_for_status()
            run_id = r.json().get("task_id") or r.json().get("id")
    except Exception as exc:  # noqa: BLE001
        return {"mode": "ERROR", "error": f"{type(exc).__name__}: {exc}"}

    # persist the run WITHOUT the leased credentials
    safe_task = json.loads(json.dumps(task))
    safe_task["navigation_payload"].pop("credentials", None)
    with Session(engine) as s:
        run = WorkflowRun(site_domain=domain, network_name=network, kind="discover",
                          operation="update", state="running",
                          dry_run_plan=json.dumps({"scout": True, "entry": entry, "task": safe_task}),
                          created_by=created_by)
        s.add(run)
        s.add(AuditLog(actor=created_by, actor_kind="agent", action="scout.submitted",
                       target=f"{domain}:{network}", detail=json.dumps({"run_id": run_id})))
        s.commit()
        s.refresh(run)
        return {"workflow_id": run.id, "run_id": run_id, "mode": "LIVE",
                "note": "read-only profile scout submitted; poll run_id, then finalize_scout()"}


def finalize_scout(run_id: str, network: str, workflow_id: int | None = None) -> dict:
    """After the scout completes, pull the extracted fields, save them as the 'profile'
    schema, and record the outcome on the workflow run."""
    from sqlmodel import Session
    from ..config import SKYVERN_API_KEY, SKYVERN_BASE_URL
    from ..db import engine
    from ..models import WorkflowRun
    from . import pipeline

    import httpx
    headers = {"x-api-key": SKYVERN_API_KEY}
    with httpx.Client(timeout=30) as c:
        t = c.get(f"{SKYVERN_BASE_URL.rstrip('/')}/api/v1/tasks/{run_id}", headers=headers).json()
    status = t.get("status")
    extracted = t.get("extracted_information") or {}
    if isinstance(extracted, list) and extracted:
        extracted = extracted[0] if isinstance(extracted[0], dict) else {"fields": extracted}
    schema = _to_schema(extracted)
    new_fields = schema["pages"][0]["fields"]
    # GUARD: don't clobber a good existing schema with a bad/partial scout (e.g. one that
    # landed on the wrong page). Only overwrite if the new scout meaningfully overlaps the
    # existing field set OR there's no existing schema. Otherwise keep the old + report.
    existing = pipeline.get_schema(network, "profile")
    if not new_fields:
        saved = {"warning": "no fields extracted — schema unchanged"}
    elif existing and existing.get("pages"):
        ex_keys = {f.get("key") for f in existing["pages"][0].get("fields", [])}
        new_keys = {f.get("key") for f in new_fields}
        overlap = len(ex_keys & new_keys)
        if ex_keys and overlap < max(2, len(ex_keys) * 0.4):
            saved = {"warning": f"scout landed on an unexpected page ({len(new_keys)} unrelated "
                                f"fields, {overlap} overlap) — schema kept, NOT overwritten",
                     "would_have_saved": sorted(new_keys)}
        else:
            saved = pipeline.set_schema(network, schema, form="profile", actor="scout")
    else:
        saved = pipeline.set_schema(network, schema, form="profile", actor="scout")

    if workflow_id:
        with Session(engine) as s:
            run = s.get(WorkflowRun, workflow_id)
            if run:
                run.result = json.dumps({"status": status, "fields": len(schema["pages"][0]["fields"]),
                                         "schema_saved": saved})
                run.state = "done" if status == "completed" else "failed"
                s.add(run); s.commit()
    return {"status": status, "fields": schema["pages"][0]["fields"], "saved": saved}
