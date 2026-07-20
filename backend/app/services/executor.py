"""Executor router — the pluggable seam between C3 and *how* a network's form gets filled.

- HEAD networks (high volume, DOM engineered) → deterministic Playwright script: fast (~20s),
  reliable, and SELF-VERIFYING (it reloads + reads back the real value).
- LONG TAIL / bot-protected / signups → Skyvern agent (has residential proxies + CAPTCHA +
  anti-detection built in).

Both flow through the same pipeline (prepare → approve → execute → verify → write-back).
Adding a network = register a script module here, or nothing (it falls back to Skyvern).

`verify_read` is the executor-AGNOSTIC independent verifier: a deterministic read of the live
account. It can verify a Skyvern execution too — that's the trustworthy read that never lies.
"""
from __future__ import annotations

from .scripts import sourceknowledge

# network name (lowercased) -> deterministic script module (exposes read_profile / update_profile)
SCRIPTS = {"sourceknowledge": sourceknowledge}


def has_script(network: str) -> bool:
    return (network or "").lower() in SCRIPTS


def execute(operation: str, domain: str, network: str, fields: dict,
            holding_company: str | None, force_live: bool = False) -> dict:
    """Run the change via the best executor for this network. Script path is SYNCHRONOUS and
    returns a self-verified result; Skyvern path is async and returns a run_id to poll."""
    key = (network or "").lower()
    if key in SCRIPTS and operation == "update":
        from . import vault
        creds = vault.lease_network_credential(holding_company or "", network)
        if "error" in creds:
            return {"mode": "BLOCKED", "engine": "script", "error": creds["error"]}
        if not force_live:
            return {"mode": "DRY-RUN", "engine": "script", "network": network,
                    "would_set": fields, "note": "deterministic script — not fired (dry-run)"}
        res = SCRIPTS[key].update_profile(creds, fields)
        res.update({"mode": "LIVE", "engine": "script"})
        return res
    # long tail / bot-protected / signups → Skyvern agent
    from . import skyvern
    from .discovery import _entry_url
    entry = _entry_url(network) if operation == "update" else skyvern.signup_url_for(network)
    return skyvern.submit_fill(operation, domain, network, fields, entry,
                               holding_company=holding_company, force_live=force_live)


def verify_read(network: str, holding_company: str | None, keys=None):
    """Independent deterministic read of the current LIVE values -> {key: value}. Works for any
    network we have a script-reader for (even if the write was done via Skyvern). None otherwise."""
    key = (network or "").lower()
    if key not in SCRIPTS:
        return None
    from . import vault
    creds = vault.lease_network_credential(holding_company or "", network)
    if "error" in creds:
        return None
    return SCRIPTS[key].read_profile(creds, keys)
