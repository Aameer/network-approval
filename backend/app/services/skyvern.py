"""Real apply agent — Skyvern remote-browser submission (dry-runnable skeleton).

Skyvern Cloud runs a headless browser that fills/uploads/submits the publisher
application form. This mirrors coupon-engine's proven adapter: POST /api/v1/tasks
with an x-api-key header + navigation_goal/payload → run_id, then poll to completion.

GUARDRAIL: nothing is sent for real until SKYVERN_LIVE=true (or a per-run force_live) AND an
entry URL is set AND creds are provided. Until then submit_fill() returns the exact task it
WOULD send, so you can inspect it without firing.
"""
from __future__ import annotations

from ..config import SKYVERN_API_KEY, SKYVERN_BASE_URL, SKYVERN_LIVE

# Per-network publisher signup / application URLs — fill as you onboard each network.
NETWORK_SIGNUP_URLS = {
    "sourceknowledge": "https://app.sourceknowledge.com/ui/signup/publisher",
    "brandreward": "",
    "admitad": "",
}


def configured() -> bool:
    return bool(SKYVERN_API_KEY and SKYVERN_BASE_URL)


def signup_url_for(network: str) -> str:
    """Resolve the signup URL from the Network registry, falling back to the seed dict."""
    try:
        from sqlmodel import Session, select
        from ..db import engine
        from ..models import Network
        with Session(engine) as s:
            for n in s.exec(select(Network)).all():
                if n.name.lower() == (network or "").lower() and n.signup_url:
                    return n.signup_url
    except Exception:
        pass
    return NETWORK_SIGNUP_URLS.get((network or "").lower(), "")


# What the fill agent reports back AFTER saving, so C3 can verify the change actually persisted.
_FILL_VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "saved_fields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "the field key from navigation_payload.fields"},
                    "persisted_value": {"type": "string",
                                        "description": "the value shown on the page AFTER saving AND reloading"},
                },
            },
        }
    },
}


def build_fill_task(operation: str, domain: str, network: str, fields: dict, entry_url: str) -> dict:
    """Fill EXACTLY the provided field->value map — create (signup) or update (settings)."""
    if operation == "update":
        goal = (
            "Log in using credentials.username and credentials.password. The fields in "
            "navigation_payload.fields may live on DIFFERENT pages/tabs (Account Details, Contact "
            "Information, Billing/Payment Information, etc.). For EACH field: go to the page it is "
            "on, set it to EXACTLY the given value (use ONLY these values — never invent or "
            "auto-fill), and do NOT touch fields that aren't listed.\n"
            "CRITICAL — THE SUBMIT BUTTON IS AT THE VERY BOTTOM OF THE PAGE. On this account the "
            "Save/Submit button is a SINGLE button located at the very BOTTOM of the page, BELOW "
            "every section (below Account Info, Contact Information, and even below any 'Devices' "
            "list or footer). After editing the field(s), you MUST SCROLL ALL THE WAY DOWN to the "
            "bottom of the page, find the 'Submit' button (it may also say Save or Update), and "
            "CLICK it. Then WAIT for a success confirmation/toast. Editing fields WITHOUT scrolling "
            "down and clicking that bottom Submit button changes NOTHING and is a total FAILURE — "
            "do not ever skip it. If the fields you changed are on more than one page/tab, submit "
            "each page the same way (edit -> scroll to bottom -> click Submit -> confirm).\n"
            "After submitting, reload the page and confirm the new values persisted. Do NOT mark "
            "the task complete until you have clicked the bottom Submit button and seen the change "
            "saved. If you cannot find a Submit button at the bottom, STOP and report that."
        )
    else:
        goal = (
            f"Register a publisher account for {domain} on {network}. Fill EACH field in "
            "navigation_payload.fields with EXACTLY the given value, and log in with "
            "credentials.username / credentials.password. NEVER invent, guess, or auto-fill any "
            "value. If a REQUIRED field has no provided value, STOP and report its label rather "
            "than making one up. Accept terms only if 'terms' is provided. Solve CAPTCHA and "
            "complete email verification if required. Then log in and confirm the account is active."
        )
    return {
        "url": entry_url,
        "navigation_goal": goal,
        "data_extraction_goal": (
            "VERIFICATION — after you have saved ALL changes, RELOAD each changed page (so you read "
            "the value PERSISTED on the server, NOT the text you just typed) and report, for EACH "
            "field key present in navigation_payload.fields, the value now shown on the page. "
            "Return them as saved_fields (key + persisted_value)."
        ),
        "extracted_information_schema": _FILL_VERIFY_SCHEMA,
        "navigation_payload": {"fields": fields, "website": f"https://{domain}"},
        "proxy_location": "RESIDENTIAL",
        "max_steps_per_run": 30,   # fill + save + reload + read-back verification needs headroom
    }


def submit_fill(operation: str, domain: str, network: str, fields: dict, entry_url: str,
                holding_company=None, force_live: bool = False) -> dict:
    task = build_fill_task(operation, domain, network, fields, entry_url)
    if not (SKYVERN_LIVE or force_live):
        return {"mode": "DRY-RUN", "engine": "skyvern", "operation": operation,
                "entry_url": entry_url, "task": task,
                "note": "not live — these are the EXACT fields/values that WOULD be set."}
    if not configured():
        return {"mode": "BLOCKED", "error": "Skyvern not configured"}
    if not entry_url:
        return {"mode": "BLOCKED", "error": f"no entry URL for '{network}'"}
    from . import vault
    if holding_company:
        leased = vault.lease_network_credential(holding_company, network)
        if "error" in leased:
            return {"mode": "BLOCKED", "error": leased["error"]}
        task["navigation_payload"]["credentials"] = {
            "username": leased["username"], "password": leased["password"]}
    try:
        import httpx
        headers = {"x-api-key": SKYVERN_API_KEY, "Content-Type": "application/json"}
        with httpx.Client(timeout=60) as c:
            r = c.post(f"{SKYVERN_BASE_URL.rstrip('/')}/api/v1/tasks", headers=headers, json=task)
            r.raise_for_status()
            data = r.json()
        run_id = data.get("task_id") or data.get("id")
        return {"mode": "LIVE", "engine": "skyvern", "operation": operation, "run_id": run_id,
                "status": "submitted", "note": "poll run_id for completion + screenshots."}
    except Exception as exc:  # noqa: BLE001
        return {"mode": "ERROR", "error": f"{type(exc).__name__}: {exc}"}


