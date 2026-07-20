"""Reliability report — the head/tail scorecard.

Aggregates every LIVE execution (script + Skyvern) per network×engine from the runs' recorded
verification data, so you can SEE the difference the deterministic 'head' scripts make: their
success rate, their speed, and — crucially — whether verification was INDEPENDENT (we read the
live account ourselves) or merely the agent's self-report. This is what tells us which networks
are safe to automate and which still need script engineering.
"""
from __future__ import annotations

import json

from sqlmodel import Session, select

from ..db import engine as _db
from ..models import WorkflowRun

# Terminal states of a run that was actually fired at the network (not a dry-run/gate state).
_LIVE_STATES = {"done", "unverified", "failed"}


def _engine_of(res: dict) -> str:
    if res.get("engine"):
        return res["engine"]
    return "skyvern" if res.get("run_id") else "script"


def _verify_source(res: dict, eng: str) -> str:
    vs = res.get("verify_source")
    if vs:
        return vs
    # A deterministic script always reloads + reads back itself → independent by construction.
    return "independent-read" if eng == "script" else "agent-readback"


def report() -> dict:
    """Per network×engine reliability stats across all LIVE runs, plus overall totals."""
    with Session(_db) as s:
        runs = s.exec(select(WorkflowRun).where(WorkflowRun.operation.is_not(None))
                      .order_by(WorkflowRun.id)).all()

    groups: dict[tuple, dict] = {}
    for r in runs:
        if r.state not in _LIVE_STATES:
            continue
        res = json.loads(r.result or "{}")
        if res.get("mode") == "DRY-RUN":
            continue
        eng = _engine_of(res)
        noop = res.get("mode") == "NOOP"
        key = (r.network_name or "?", eng)
        g = groups.setdefault(key, {"network": r.network_name or "?", "engine": eng,
                                    "runs": 0, "verified": 0, "noop": 0, "unverified": 0,
                                    "failed": 0, "secs": [], "independent": 0, "last_run": None})
        g["runs"] += 1
        g["last_run"] = r.id
        if r.state == "done" and noop:
            g["noop"] += 1
        elif r.state == "done":
            g["verified"] += 1
        elif r.state == "unverified":
            g["unverified"] += 1
        elif r.state == "failed":
            g["failed"] += 1
        if _verify_source(res, eng) == "independent-read":
            g["independent"] += 1
        if isinstance(res.get("seconds"), (int, float)):
            g["secs"].append(res["seconds"])

    rows = []
    for g in groups.values():
        ok = g["verified"] + g["noop"]                 # a no-op is a successful reconcile (nothing to do)
        secs = g["secs"]
        rows.append({
            "network": g["network"], "engine": g["engine"], "runs": g["runs"],
            "verified": g["verified"], "noop": g["noop"], "unverified": g["unverified"],
            "failed": g["failed"], "last_run": g["last_run"],
            "success_pct": round(100 * ok / g["runs"]) if g["runs"] else 0,
            "independent_pct": round(100 * g["independent"] / g["runs"]) if g["runs"] else 0,
            "avg_secs": round(sum(secs) / len(secs), 1) if secs else None,
        })
    # Head (script) engines first, then by most runs.
    rows.sort(key=lambda x: (x["engine"] != "script", -x["runs"]))

    tot_runs = sum(x["runs"] for x in rows)
    tot_ok = sum(x["verified"] + x["noop"] for x in rows)
    return {
        "rows": rows,
        "totals": {"runs": tot_runs, "success_pct": round(100 * tot_ok / tot_runs) if tot_runs else 0,
                   "networks": len({x["network"] for x in rows})},
    }
