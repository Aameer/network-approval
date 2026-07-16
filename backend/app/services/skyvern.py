"""Real apply agent — Skyvern remote-browser submission (dry-runnable skeleton).

Skyvern Cloud runs a headless browser that fills/uploads/submits the publisher
application form. This mirrors coupon-engine's proven adapter: POST /api/v1/tasks
with an x-api-key header + navigation_goal/payload → run_id, then poll to completion.

GUARDRAIL: nothing is sent for real until SKYVERN_LIVE=true AND a signup URL is set
AND creds are provided. Until then submit_application() returns the exact task it
WOULD send, so you can inspect it without firing.
"""
from __future__ import annotations

from ..config import SKYVERN_API_KEY, SKYVERN_BASE_URL, SKYVERN_LIVE

# Per-network publisher signup / application URLs — fill as you onboard each network.
NETWORK_SIGNUP_URLS = {
    "sourceknowledge": "https://app.sourceknowledge.com/user/signup/affiliate",
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


def build_task(domain: str, network: str, plan: dict, creds_ref=None) -> dict:
    """The exact Skyvern task payload — built without sending it."""
    url = signup_url_for(network)
    fa = plan.get("form_answers", {}) if isinstance(plan, dict) else {}
    return {
        "url": url,
        "navigation_goal": (
            f"Register a publisher account for the website {domain} on the {network} network using "
            "the provided email and password. Accept the terms if asked. If a CAPTCHA appears, solve "
            "it. If an email verification link/code is required, complete it. Then log in with the "
            "same credentials and confirm the account is active. Capture a screenshot of the "
            "logged-in account dashboard."
        ),
        "navigation_payload": {
            "website": f"https://{domain}",
            "holding_company": plan.get("holding_company"),
            "email": plan.get("email"),
            "website_type": fa.get("website_type"),
            "traffic_sources": fa.get("traffic_sources"),
            "regions": fa.get("regions"),
            "disclosure": fa.get("disclosure"),
            "documents": plan.get("documents"),
            "credentials_ref": creds_ref,  # leased from vault at runtime — never the secret itself
        },
        "proxy_location": "RESIDENTIAL",  # route via residential proxy (BrightData) to avoid fraud flags
    }


def submit_application(domain: str, network: str, plan: dict, holding_company=None, creds_ref=None) -> dict:
    task = build_task(domain, network, plan, creds_ref)

    if not SKYVERN_LIVE:
        return {
            "mode": "DRY-RUN", "engine": "skyvern", "would_submit": True,
            "signup_url_set": bool(task["url"]),
            "task": task,
            "note": "SKYVERN_LIVE=false — this is the exact task that WOULD be sent to Skyvern's "
                    "remote browser. Go live by: set SKYVERN_LIVE=true, add the signup URL in "
                    "NETWORK_SIGNUP_URLS, provide the account creds (vault), and Murtaza sign-off.",
        }
    if not configured():
        return {"mode": "BLOCKED", "error": "Skyvern not configured (SKYVERN_API_KEY / SKYVERN_BASE_URL)"}
    if not task["url"]:
        return {"mode": "BLOCKED", "error": f"no signup URL configured for '{network}' in NETWORK_SIGNUP_URLS"}

    # Lease the network login just-in-time — never stored in the plan/DB, only sent to
    # Skyvern over TLS at submit time.
    from . import vault
    if holding_company:
        leased = vault.lease_network_credential(holding_company, network)
        if "error" in leased:
            return {"mode": "BLOCKED",
                    "error": leased["error"] + " — store it via POST /api/network-credentials first"}
        task["navigation_payload"]["credentials"] = {
            "username": leased["username"], "password": leased["password"]}

    # --- LIVE path: create the remote-browser run (async; a worker polls to completion) ---
    try:
        import httpx
        headers = {"x-api-key": SKYVERN_API_KEY, "Content-Type": "application/json"}
        with httpx.Client(timeout=60) as c:
            r = c.post(f"{SKYVERN_BASE_URL.rstrip('/')}/api/v1/tasks", headers=headers, json=task)
            r.raise_for_status()
            data = r.json()
        run_id = data.get("task_id") or data.get("id")
        # Skyvern is async — poll GET /api/v1/tasks/{run_id} for completion + screenshots
        # (mirror coupon-engine verification.tasks.poll_task_once). Status flips to approved
        # later when the approval email is parsed.
        return {"mode": "LIVE", "engine": "skyvern", "run_id": run_id,
                "status": "submitted_pending_review",
                "note": "Skyvern remote-browser run created; poll run_id for completion + screenshots."}
    except Exception as exc:  # noqa: BLE001
        return {"mode": "ERROR", "error": f"{type(exc).__name__}: {exc}"}
