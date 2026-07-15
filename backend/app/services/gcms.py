"""Minimal GCMS GraphQL client — session-token auth, read-only for the PoC.

Creds come from env (GCMS_GRAPHQL_ENDPOINT / GCMS_USERNAME / GCMS_PASSWORD). Those
values already exist in coupon-svp/.env; copy them into backend/.env. If unset, the
client returns a clear "not configured" marker so the copilot degrades gracefully.
"""
from __future__ import annotations

import httpx

from ..config import GCMS_GRAPHQL_ENDPOINT, GCMS_PASSWORD, GCMS_USERNAME

_AUTH = """
mutation($email:String!,$password:String!){
  authenticateUserWithPassword(email:$email,password:$password){
    ... on UserAuthenticationWithPasswordSuccess { sessionToken }
    ... on UserAuthenticationWithPasswordFailure { message }
  }
}"""

# Keep the field set small + defensive; GCMS is a Keystone schema (Property list).
_SITE = """
query($where: PropertyWhereInput!){
  properties(where:$where, take:1){
    name code homePage legalEntityName GoogleTagId WeCanTrackId
    regions { code } categories { name }
  }
}"""


def is_configured() -> bool:
    return bool(GCMS_GRAPHQL_ENDPOINT and GCMS_USERNAME and GCMS_PASSWORD)


def _token(client: httpx.Client) -> str | None:
    r = client.post(GCMS_GRAPHQL_ENDPOINT, json={
        "query": _AUTH,
        "variables": {"email": GCMS_USERNAME, "password": GCMS_PASSWORD},
    })
    r.raise_for_status()
    data = r.json().get("data", {}).get("authenticateUserWithPassword", {}) or {}
    return data.get("sessionToken")


def get_site(domain: str) -> dict:
    """Fetch live site truth from GCMS by homePage/domain. Returns a dict the copilot can read."""
    if not is_configured():
        return {"configured": False,
                "note": "GCMS creds not set in backend/.env — copy from coupon-svp/.env to enable live reads."}
    try:
        with httpx.Client(timeout=20) as client:
            token = _token(client)
            if not token:
                return {"configured": True, "error": "GCMS auth failed (check GCMS_USERNAME/PASSWORD)."}
            client.cookies.set("keystonejs-session", token)
            # match on homePage containing the domain (schema-dependent; best-effort for PoC)
            r = client.post(GCMS_GRAPHQL_ENDPOINT, json={
                "query": _SITE,
                "variables": {"where": {"homePage": {"contains": domain}}},
            })
            r.raise_for_status()
            props = r.json().get("data", {}).get("properties") or []
            if not props:
                return {"configured": True, "found": False, "domain": domain}
            return {"configured": True, "found": True, "site": props[0]}
    except Exception as exc:  # noqa: BLE001 - degrade gracefully for the copilot
        return {"configured": True, "error": f"{type(exc).__name__}: {exc}"}
