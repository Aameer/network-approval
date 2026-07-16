"""Signup-URL discovery — lightweight skeleton.

In production this web-searches "{network} affiliate publisher signup", fetches the top
candidates, confirms each is a self-serve publisher signup form, and — crucially —
validates it sits on the network's OFFICIAL registrable domain before caching it.
Discover once, cache in the Network registry, reuse everywhere.

Here it returns the plan + the domain guardrail; wire a search API to make it live.
"""
from __future__ import annotations

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
