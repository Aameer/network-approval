"""The reconcile pipeline:  scout (discover) -> prepare -> [human approves] -> execute.

Create vs update is the SAME flow — only the scouted page (signup vs profile) and
whether we log in first differ. The Prepare step answers EVERY discovered form field
from our own DB (BillingProfile / Site / credential). Nothing is ever invented: a field
with no source value is flagged MISSING and the run cannot be approved until it's filled.
"""
from __future__ import annotations

import json
from datetime import datetime

from sqlmodel import Session, select

from ..db import engine
from ..models import (
    AuditLog, BillingProfile, Network, NetworkApplication, Site, WorkflowRun,
)
from . import vault

# Maps a discovered form-field key -> where its answer comes from.
# resolver(profile, site, cred_username) -> (value, source_label)  (value None => will flag MISSING)
_SECRET = object()  # sentinel: value is a secret, shown masked, leased at execute time


def _billing(p, attr):
    return (getattr(p, attr, None) if p else None)


def _first(p):
    n = _billing(p, "contact_name")
    return n.split()[0] if n else None


def _last(p):
    n = _billing(p, "contact_name")
    parts = n.split() if n else []
    return " ".join(parts[1:]) if len(parts) > 1 else None


FIELD_SOURCES = {
    "company_name":     lambda p, s, u: (_billing(p, "company_name") or (s.holding_company if s else None), "BillingProfile.company_name / holding_company"),
    "contact_name":     lambda p, s, u: (_billing(p, "contact_name"), "BillingProfile.contact_name"),
    "first_name":       lambda p, s, u: (_first(p), "BillingProfile.contact_name (first)"),
    "last_name":        lambda p, s, u: (_last(p), "BillingProfile.contact_name (last)"),
    "billing_name":     lambda p, s, u: (_billing(p, "contact_name"), "BillingProfile.contact_name"),
    "email":            lambda p, s, u: (u, "NetworkCredential.username"),
    "contact_email":    lambda p, s, u: (_billing(p, "contact_email") or u, "BillingProfile.contact_email"),
    "password":         lambda p, s, u: (_SECRET, "NetworkCredential.password (masked, leased at execute)"),
    "password_confirm": lambda p, s, u: (_SECRET, "NetworkCredential.password (masked, leased at execute)"),
    "website_url":      lambda p, s, u: (f"https://{s.domain}" if s else None, "Site.domain"),
    "traffic_type":     lambda p, s, u: ("Paid search", "default (form_answers)"),
    "terms":            lambda p, s, u: ("accept", "disclosure policy"),
    "phone":            lambda p, s, u: (_billing(p, "phone"), "BillingProfile.phone"),
    "country":          lambda p, s, u: (_billing(p, "country"), "BillingProfile.country"),
    "address1":         lambda p, s, u: (_billing(p, "address1"), "BillingProfile.address1"),
    "address2":         lambda p, s, u: (_billing(p, "address2"), "BillingProfile.address2"),
    "city":             lambda p, s, u: (_billing(p, "city"), "BillingProfile.city"),
    "state":            lambda p, s, u: (_billing(p, "state"), "BillingProfile.state"),
    "zip_code":         lambda p, s, u: (_billing(p, "zip_code"), "BillingProfile.zip_code"),
    "paypal_email":     lambda p, s, u: (_billing(p, "paypal_email"), "BillingProfile.paypal_email"),
    "payment_type":     lambda p, s, u: ("PayPal", "default (payout method)"),
    "tax_id":           lambda p, s, u: (_billing(p, "tax_id"), "BillingProfile.tax_id"),
}


def get_schema(network: str, form: str = "signup") -> dict | None:
    """Schema is stored per form type — 'signup' (create) vs 'profile' (update) differ."""
    with Session(engine) as s:
        for row in s.exec(select(Network)).all():
            if row.name.lower() == (network or "").lower() and row.form_schema:
                return json.loads(row.form_schema).get(form)
    return None


def set_schema(network: str, schema: dict, form: str = "signup", actor: str = "discover") -> dict:
    with Session(engine) as s:
        row = next((r for r in s.exec(select(Network)).all()
                    if r.name.lower() == network.lower()), None)
        if not row:
            return {"error": f"unknown network {network}"}
        store = json.loads(row.form_schema) if row.form_schema else {}
        store[form] = schema
        row.form_schema = json.dumps(store)
        row.form_schema_at = datetime.utcnow()
        s.add(row)
        s.add(AuditLog(actor=actor, actor_kind="agent", action="form.schema_saved",
                       target=f"{network}:{form}", detail=json.dumps({"fields": _count_fields(schema)})))
        s.commit()
        return {"network": network, "form": form, "fields": _count_fields(schema)}


def _count_fields(schema: dict) -> int:
    return sum(len(pg.get("fields", [])) for pg in schema.get("pages", []))


def _iter_fields(schema: dict):
    for pg in schema.get("pages", []):
        for f in pg.get("fields", []):
            yield pg.get("page", 1), f


def _resolve(schema: dict, profile, site, cred_user, hc: str, network: str):
    """Resolve every discovered field from our DB -> (answers, blockers). A blocker is a
    required field that is missing OR a password that isn't valid (alphanumeric)."""
    pw_ok = vault.network_credential_password_ok(hc, network)
    answers, blockers = [], []
    for page, f in _iter_fields(schema):
        key, label, required = f.get("key"), f.get("label", f.get("key")), f.get("required", False)
        if key in ("password", "password_confirm"):
            source = "NetworkCredential.password (masked, leased at execute)"
            if not cred_user:
                shown, status = None, "MISSING"
                blockers.append(label)
            elif not pw_ok:
                shown, status = "•••• (INVALID — must be alphanumeric)", "INVALID"
                blockers.append(label)
            else:
                shown, status = "•••• (leased at execute)", "ready"
        else:
            src = FIELD_SOURCES.get(key)
            value, source = (src(profile, site, cred_user) if src else (None, "unmapped"))
            if value and value is not _SECRET:
                shown, status = value, "ready"
            else:
                shown, status = None, ("MISSING" if required else "optional-empty")
                if required:
                    blockers.append(label)
        answers.append({"page": page, "key": key, "label": label, "required": required,
                        "value": shown, "source": source, "status": status,
                        "current_value": f.get("current_value"),
                        "type": f.get("type"), "rule": f.get("rule")})
    return answers, blockers


def check_ready(domain: str, network: str, operation: str = "create") -> dict:
    """Re-validate LIVE against the current DB (used at approval time so a just-filled
    field is honored, instead of trusting the snapshot taken when Prepare ran)."""
    form = "profile" if operation == "update" else "signup"
    schema = get_schema(network, form)
    if not schema:
        return {"ready": False, "blockers": [f"no '{form}' form schema"]}
    with Session(engine) as s:
        site = s.exec(select(Site).where(Site.domain == domain)).first()
        if not site:
            return {"ready": False, "blockers": ["unknown site"]}
        profile = s.exec(select(BillingProfile).where(
            BillingProfile.holding_company == (site.holding_company or ""))).first()
        cred_user = vault.network_credential_username(site.holding_company or "", network)
        _, blockers = _resolve(schema, profile, site, cred_user, site.holding_company or "", network)
        return {"ready": len(blockers) == 0, "blockers": blockers}


def sheet_fields(run_id: int) -> dict:
    """The EXACT field->value map to submit, read from the run's RunAnswer rows (the sheet
    is the source of truth — WYSIWYG). Password rows excluded (leased at submit); empty,
    masked, and optional-empty rows skipped."""
    from ..models import RunAnswer
    with Session(engine) as s:
        rows = s.exec(select(RunAnswer).where(RunAnswer.run_id == run_id)).all()
    out = {}
    for r in rows:
        if r.field_key in ("password", "password_confirm"):
            continue
        v = r.value
        if v is None:
            continue
        if isinstance(v, str) and (not v.strip() or v.startswith("••••")):
            continue
        out[r.field_key] = v
    return out


def defaults_for_run(run_id: int) -> dict:
    """{field_key: default_value} re-resolved from Billing Profile — used by 'Revert to default'."""
    with Session(engine) as s:
        run = s.get(WorkflowRun, run_id)
        if not run:
            return {}
        site = s.exec(select(Site).where(Site.domain == run.site_domain)).first()
        if not site:
            return {}
        profile = s.exec(select(BillingProfile).where(
            BillingProfile.holding_company == (site.holding_company or ""))).first()
        cred_user = vault.network_credential_username(site.holding_company or "", run.network_name)
    form = "profile" if run.operation == "update" else "signup"
    schema = get_schema(run.network_name, form)
    if not schema:
        return {}
    answers, _ = _resolve(schema, profile, site, cred_user, site.holding_company or "", run.network_name)
    return {a["key"]: a["value"] for a in answers}


# field_key -> BillingProfile attr for write-back (first/last handled specially; website/email/
# password/terms/traffic are NOT owned by the profile, so they never write back to it).
_WRITEBACK_MAP = {
    "company_name": "company_name", "contact_name": "contact_name", "contact_email": "contact_email",
    "phone": "phone", "address1": "address1", "address2": "address2", "city": "city",
    "state": "state", "zip_code": "zip_code", "country": "country",
    "paypal_email": "paypal_email", "tax_id": "tax_id",
}


def write_back(run_id: int, fields: dict, actor: str = "system") -> dict:
    """After a SUCCESSFUL execution, make our records match what we just wrote to the network:
    update the network mirror (form_schema current_values) + the Billing Profile (mapped fields)."""
    with Session(engine) as s:
        run = s.get(WorkflowRun, run_id)
        if not run:
            return {"error": "run not found"}
        site = s.exec(select(Site).where(Site.domain == run.site_domain)).first()
        hc = (site.holding_company if site else "") or ""
        form = "profile" if run.operation == "update" else "signup"

        # 1) network mirror — set current_value to the submitted value
        net = next((r for r in s.exec(select(Network)).all()
                    if r.name.lower() == (run.network_name or "").lower()), None)
        mirror_n = 0
        if net and net.form_schema:
            store = json.loads(net.form_schema)
            sch = store.get(form)
            if sch:
                for pg in sch.get("pages", []):
                    for f in pg.get("fields", []):
                        if f.get("key") in fields:
                            f["current_value"] = fields[f["key"]]
                            mirror_n += 1
                store[form] = sch
                net.form_schema = json.dumps(store)
                net.form_schema_at = datetime.utcnow()
                s.add(net)

        # 2) Billing Profile — mapped fields (first+last -> contact_name)
        prof = s.exec(select(BillingProfile).where(BillingProfile.holding_company == hc)).first()
        prof_n = 0
        if prof:
            first, last = fields.get("first_name"), fields.get("last_name")
            if first or last:
                prof.contact_name = " ".join(x for x in (first, last) if x) or prof.contact_name
                prof_n += 1
            for key, attr in _WRITEBACK_MAP.items():
                if fields.get(key) is not None:
                    setattr(prof, attr, fields[key])
                    prof_n += 1
            s.add(prof)

        # 3) refresh THIS run's sheet rows so they show the converged state (not stale live values)
        from ..models import RunAnswer
        for row in s.exec(select(RunAnswer).where(RunAnswer.run_id == run_id)).all():
            if row.field_key in fields:
                row.current_value = fields[row.field_key]
                s.add(row)

        s.add(AuditLog(actor=actor, actor_kind="system", action="apply.writeback",
                       target=f"{run.site_domain}:{run.network_name}",
                       detail=json.dumps({"mirror_fields": mirror_n, "profile_fields": prof_n})))
        s.commit()
    return {"mirror_fields": mirror_n, "profile_fields": prof_n}


def fields_to_submit(run_id: int) -> dict:
    """The fields to actually send to the agent. For UPDATE we send ONLY the fields that DIFFER
    from what's live (no point re-typing values that already match — it just wastes steps and
    risks touching unrelated pages). For CREATE we send everything (nothing exists yet)."""
    from ..models import RunAnswer, WorkflowRun
    with Session(engine) as s:
        run = s.get(WorkflowRun, run_id)
        op = (run.operation if run else "create") or "create"
        rows = s.exec(select(RunAnswer).where(RunAnswer.run_id == run_id)).all()
    out = {}
    for r in rows:
        if r.field_key in ("password", "password_confirm"):
            continue
        v = r.value
        if v is None:
            continue
        if isinstance(v, str) and (not v.strip() or v.startswith("••••")):
            continue
        if op == "update" and str(v).strip() == str(r.current_value or "").strip():
            continue  # already matches the network — nothing to change
        out[r.field_key] = v
    return out


def check_run_ready(run_id: int) -> dict:
    """Validate the SHEET itself (RunAnswer rows) — every required row has a non-empty value,
    and the password (not on the sheet) is present + valid. This is what Approve/Execute gate on,
    so 'what's checked == what's on the sheet == what submits'."""
    from ..models import RunAnswer
    with Session(engine) as s:
        run = s.get(WorkflowRun, run_id)
        if not run:
            return {"ready": False, "blockers": ["run not found"]}
        rows = s.exec(select(RunAnswer).where(RunAnswer.run_id == run_id)).all()
        site = s.exec(select(Site).where(Site.domain == run.site_domain)).first()
        hc = (site.holding_company if site else "") or ""
        pw_ok = vault.network_credential_password_ok(hc, run.network_name or "")
    blockers = []
    for r in rows:
        if not r.required:
            continue
        if r.field_key in ("password", "password_confirm"):
            if not pw_ok:
                blockers.append(r.label)
        else:
            v = r.value.strip() if isinstance(r.value, str) else r.value
            if not v:
                blockers.append(r.label)
    return {"ready": len(blockers) == 0, "blockers": blockers}


def infer_operation(domain: str, network: str) -> str:
    """'update' if we already hold an approved/applied account on this network, else 'create'."""
    with Session(engine) as s:
        site = s.exec(select(Site).where(Site.domain == domain)).first()
        if not site:
            return "create"
        for a in s.exec(select(NetworkApplication).where(
                NetworkApplication.site_id == site.id)).all():
            if (a.network_name or "").lower() == network.lower() and a.status.value in ("approved", "applied"):
                return "update"
    return "create"


def prepare(domain: str, network: str, operation: str = "create",
            created_by: str = "console") -> dict:
    """Build the answer sheet by resolving every discovered field from our DB, then file
    a GATED WorkflowRun. Required fields with no source value are flagged MISSING — the
    run is filed but marked not-ready (cannot execute) until they're supplied."""
    form = "profile" if operation == "update" else "signup"
    schema = get_schema(network, form)
    if not schema:
        return {"error": f"no '{form}' form schema for {network} — run Discover (scout) first"}

    with Session(engine) as s:
        site = s.exec(select(Site).where(Site.domain == domain)).first()
        if not site:
            return {"error": f"unknown site {domain}"}
        profile = s.exec(select(BillingProfile).where(
            BillingProfile.holding_company == (site.holding_company or ""))).first()
        cred_user = vault.network_credential_username(site.holding_company or "", network)

        answers, blockers = _resolve(schema, profile, site, cred_user,
                                     site.holding_company or "", network)
        ready = len(blockers) == 0
        # Meta only — the answer sheet itself is the RunAnswer rows (single source of truth).
        plan = {
            "operation": operation, "site": domain, "network": network,
            "holding_company": site.holding_company,
            "ready_to_execute": ready, "missing_required": blockers,
            "note": ("all required fields resolved — safe to approve" if ready else
                     f"{len(blockers)} field(s) block approval (missing/invalid): {', '.join(blockers)}"),
        }
        run = WorkflowRun(site_domain=domain, network_name=network, kind="apply",
                          operation=operation, state="awaiting_approval",
                          dry_run_plan=json.dumps(plan), created_by=created_by)
        s.add(run)
        s.add(AuditLog(actor=created_by, actor_kind="agent", action="apply.prepared",
                       target=f"{domain}:{network}",
                       detail=json.dumps({"operation": operation, "ready": ready, "missing": blockers})))
        s.commit()
        s.refresh(run)
        # Persist each answer as its own row — the human-readable, overridable sheet.
        from ..models import RunAnswer
        for a in answers:
            s.add(RunAnswer(run_id=run.id, page=a["page"], field_key=a["key"], label=a["label"],
                            value=a["value"], current_value=a.get("current_value"),
                            status=a["status"], source=a["source"], required=a["required"]))
        s.commit()
        return {"workflow_id": run.id, "state": run.state, "operation": operation,
                "ready_to_execute": ready, "missing_required": blockers, "plan": plan}
