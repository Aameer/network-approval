"""starlette-admin data browser — read-only, password-gated, encrypted columns hidden.

Mounted at /admin. Richer than sqladmin (better UI, field types, custom actions available
later). Everything read-only for now; sensitive columns (password_enc/value_enc) are simply
not listed as fields, so they never surface.
"""
from __future__ import annotations

from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette_admin import StringField, URLField
from starlette_admin.actions import action
from starlette_admin.auth import AdminUser, AuthProvider
from starlette_admin.contrib.sqla import Admin, ModelView
from starlette_admin.exceptions import ActionFailed, LoginFailed
from starlette_admin.views import Link

from .config import ADMIN_PANEL_PASSWORD, SESSION_SECRET
from .db import engine
from .models import (
    AuditLog, BillingProfile, Network, NetworkApplication, NetworkCredential, RunAnswer,
    Site, SiteSecret, User, WorkflowRun,
)


def _audit_override(obj):
    """Log an admin-panel override to the AuditLog (raw edits must still be audited)."""
    from sqlmodel import Session
    from .db import engine as _e
    from .models import AuditLog as _A
    with Session(_e) as s:
        s.add(_A(actor="admin-panel", actor_kind="human", action="admin.override",
                 target=f"{type(obj).__name__}:{getattr(obj, 'id', '?')}", detail="{}"))
        s.commit()


class _RO:
    """Read-only view."""
    page_size = 50
    page_size_options = [25, 50, 100, 200]

    def can_create(self, request) -> bool:
        return False

    def can_edit(self, request) -> bool:
        return False

    def can_delete(self, request) -> bool:
        return False


class _Override:
    """Editable (override) + audited; no create/delete."""
    page_size = 50
    page_size_options = [25, 50, 100, 200]

    def can_create(self, request) -> bool:
        return False

    def can_delete(self, request) -> bool:
        return False

    async def after_edit(self, request, obj) -> None:
        _audit_override(obj)


class SiteView(_Override, ModelView):
    fields = ["id", "domain", "holding_company", "site_category", "website_type",
              "website_status", "country", "phase", "is_sandbox", "redirection_status",
              "clickout_moved", "ga4_property_id", "wct_user_website_id", "gtm_tag",
              "mcc_id", "mcc_admin_email", "persona", "registered_on", "domain_expiry",
              "privacy_protection", "repo", "repo_link", "repo_criticality", "repo_status",
              "vercel_project", "notes", "raw"]
    exclude_fields_from_list = ["raw"]  # full original row — shown in the detail view only
    searchable_fields = ["domain", "holding_company", "mcc_admin_email"]
    column_sortable_list = ["domain", "holding_company", "phase", "country"]


class NetworkView(_Override, ModelView):
    fields = ["id", "name", "phase", "status", "signup_url", "login_url"]


class NetworkApplicationView(_Override, ModelView):
    fields = ["id", "site", "network_name", "status", "publisher_id",
              "submission_date", "next_followup_date", "rejection_reason"]
    label = "Network Applications"
    actions = ["prepare_sheet"]

    @action(name="prepare_sheet", text="📝 Prepare approval sheet",
            confirmation="Scout schema + resolve our data into a fresh, gated approval sheet "
                         "(create vs update inferred from status). Nothing is submitted.",
            submit_btn_text="Prepare", submit_btn_class="btn-primary")
    async def prepare_sheet(self, request, pks):
        from sqlmodel import Session
        from .db import engine as _e
        from .models import NetworkApplication as _NA, Site as _S
        from .services import pipeline
        out = []
        with Session(_e) as s:
            for pk in pks:
                app = s.get(_NA, int(pk))
                site = s.get(_S, app.site_id) if app else None
                if not site:
                    continue
                op = pipeline.infer_operation(site.domain, app.network_name)
                r = pipeline.prepare(site.domain, app.network_name, operation=op, created_by="admin-panel")
                if "error" in r:
                    raise ActionFailed(f"{site.domain}×{app.network_name}: {r['error']}")
                out.append(f"#{r['workflow_id']} {app.network_name} ({op})")
        return "Prepared: " + "; ".join(out) + " — see Workflow Runs / Approval Sheet"


class WorkflowView(_RO, ModelView):
    fields = ["id", "site_domain", "network_name", "kind", "operation", "state", "created_by",
              "created_at", "dry_run_plan", "result"]
    exclude_fields_from_list = ["dry_run_plan", "result"]  # big JSON — shown in detail only
    label = "Workflow Runs"
    actions = ["approve", "reject", "execute_dryrun"]

    @action(name="approve", text="✅ Approve (gate)",
            confirmation="Run the approval gate on the selected run(s)? "
                         "It re-checks required data live and will refuse if anything is missing. "
                         "This does NOT execute — it only marks the run approved.",
            submit_btn_text="Approve", submit_btn_class="btn-success")
    async def approve(self, request, pks):
        from .services.apply import approve_prepared
        done = []
        for pk in pks:
            r = approve_prepared(int(pk), approver="admin-panel")
            if "error" in r:
                raise ActionFailed(f"#{pk}: {r['error']}")
            done.append(f"#{pk} → {r['state']}")
        return "Approved: " + "; ".join(done)

    @action(name="reject", text="✖ Reject",
            confirmation="Reject the selected run(s)?",
            submit_btn_text="Reject", submit_btn_class="btn-danger")
    async def reject(self, request, pks):
        from .services.apply import reject_run
        for pk in pks:
            reject_run(int(pk), actor="admin-panel", reason="rejected in admin")
        return f"Rejected {len(pks)} run(s)"

    @action(name="execute_dryrun", text="🧪 Execute (dry-run)",
            confirmation="Preview execution: re-resolves live values and shows the EXACT fields "
                         "that would be submitted. Nothing is sent to the live account.",
            submit_btn_text="Preview", submit_btn_class="btn-primary")
    async def execute_dryrun(self, request, pks):
        from .services.apply import execute_run
        out = []
        for pk in pks:
            r = execute_run(int(pk), actor="admin-panel", force_live=False)
            if "error" in r:
                raise ActionFailed(f"#{pk}: {r['error']}")
            out.append(f"#{pk} → {r['mode']}")
        return "Dry-run: " + "; ".join(out) + " (open the run's Result to see the fields)"


class RunAnswerView(_Override, ModelView):
    """The approval sheet — EDITABLE, WYSIWYG: `value` is exactly what gets submitted.
    Only `value` is editable; everything else is context. `changed` flags where our value
    differs from what's live on the network. Row actions: Revert to default / Pull from live."""
    fields = ["id", "run", "page", "label", "field_key", "current_value", "value",
              StringField("changed", label="", read_only=True), "status", "source", "required"]
    exclude_fields_from_edit = ["run", "page", "label", "field_key", "current_value",
                                "changed", "status", "source", "required"]
    label = "Approval Sheet"
    searchable_fields = ["label", "field_key", "status"]
    actions = ["revert_default", "pull_from_live"]

    @action(name="revert_default", text="↺ Revert to default",
            confirmation="Reset the selected field(s)' value to the Billing Profile default?",
            submit_btn_text="Revert", submit_btn_class="btn-secondary")
    async def revert_default(self, request, pks):
        from sqlmodel import Session, select as _sel
        from .db import engine as _e
        from .models import RunAnswer as _RA
        from .services import pipeline
        n = 0
        with Session(_e) as s:
            cache = {}
            for pk in pks:
                row = s.get(_RA, int(pk))
                if not row or row.field_key in ("password", "password_confirm"):
                    continue
                if row.run_id not in cache:
                    cache[row.run_id] = pipeline.defaults_for_run(row.run_id)
                row.value = cache[row.run_id].get(row.field_key)
                s.add(row); n += 1
            s.commit()
        return f"Reverted {n} field(s) to default"

    @action(name="pull_from_live", text="⬇ Pull from live",
            confirmation="Set the selected field(s)' value to what's currently live on the network?",
            submit_btn_text="Pull", submit_btn_class="btn-secondary")
    async def pull_from_live(self, request, pks):
        from sqlmodel import Session
        from .db import engine as _e
        from .models import RunAnswer as _RA
        n = 0
        with Session(_e) as s:
            for pk in pks:
                row = s.get(_RA, int(pk))
                if not row:
                    continue
                row.value = row.current_value
                s.add(row); n += 1
            s.commit()
        return f"Pulled {n} field(s) from live"


class AuditView(_RO, ModelView):
    fields = ["id", "actor_kind", "actor", "action", "target", "created_at"]


class NetworkCredentialView(_Override, ModelView):
    # password decrypts in detail, editable in the edit form (encrypted on save); hidden from list
    fields = ["id", "holding_company", "network", "username",
              StringField("password", label="Password (decrypted)", exclude_from_list=True)]


class SiteSecretView(_Override, ModelView):
    # value decrypts in detail, editable in the edit form (re-encrypted on save); hidden from list
    fields = ["id", "site", "field",
              StringField("value", label="Value (decrypted)", exclude_from_list=True)]
    label = "Site Secrets"


class BillingProfileView(_Override, ModelView):
    """The complete real account profile per holding company — ops fills this; the Prepare
    step answers every form field from here. Editable + creatable, audited, no delete."""
    fields = ["id", "holding_company", "company_name", "contact_name", "contact_email",
              "phone", "address1", "address2", "city", "state", "zip_code", "country",
              "paypal_email", "tax_id", "extra", "notes"]
    label = "Billing Profiles"
    searchable_fields = ["holding_company", "company_name", "paypal_email"]

    def can_create(self, request) -> bool:   # ops needs to add profiles for new holding cos
        return True


class UserView(_RO, ModelView):
    fields = ["id", "email", "name", "role", "created_at"]


class AdminAuth(AuthProvider):
    async def login(self, username, password, remember_me, request, response):
        if ADMIN_PANEL_PASSWORD and password == ADMIN_PANEL_PASSWORD:
            request.session.update({"admin": True})
            return response
        raise LoginFailed("Invalid credentials")

    async def is_authenticated(self, request) -> bool:
        return bool(request.session.get("admin"))

    def get_admin_user(self, request):
        return AdminUser(username="admin")

    async def logout(self, request, response):
        request.session.clear()
        return response


def setup_admin(app):
    if not ADMIN_PANEL_PASSWORD:
        return
    admin = Admin(
        engine, title="C3 Admin", auth_provider=AdminAuth(),
        middlewares=[Middleware(SessionMiddleware, secret_key=SESSION_SECRET)],
    )
    # Approval Review (the single-page sheet UI) sits at the top — the primary daily surface.
    admin.add_view(Link(label="Approval Review", icon="fa fa-clipboard-check", url="/review"))
    admin.add_view(SiteView(Site))
    admin.add_view(NetworkView(Network))
    admin.add_view(NetworkApplicationView(NetworkApplication))
    admin.add_view(WorkflowView(WorkflowRun))
    admin.add_view(AuditView(AuditLog))
    admin.add_view(NetworkCredentialView(NetworkCredential))
    admin.add_view(SiteSecretView(SiteSecret))
    admin.add_view(BillingProfileView(BillingProfile))
    admin.add_view(UserView(User))
    admin.mount_to(app)
