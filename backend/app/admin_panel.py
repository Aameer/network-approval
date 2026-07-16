"""starlette-admin data browser — read-only, password-gated, encrypted columns hidden.

Mounted at /admin. Richer than sqladmin (better UI, field types, custom actions available
later). Everything read-only for now; sensitive columns (password_enc/value_enc) are simply
not listed as fields, so they never surface.
"""
from __future__ import annotations

from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette_admin.auth import AdminUser, AuthProvider
from starlette_admin.contrib.sqla import Admin, ModelView
from starlette_admin.exceptions import LoginFailed

from .config import ADMIN_PANEL_PASSWORD, SESSION_SECRET
from .db import engine
from .models import (
    AuditLog, Network, NetworkApplication, NetworkCredential, Site, SiteSecret,
    User, WorkflowRun,
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
    def can_create(self, request) -> bool:
        return False

    def can_edit(self, request) -> bool:
        return False

    def can_delete(self, request) -> bool:
        return False


class _Override:
    """Editable (override) + audited; no create/delete."""
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

    async def __admin_repr__(self, request, obj):
        return f"{obj.domain} · {obj.holding_company or '—'}"

    async def __admin_select2_repr__(self, request, obj):
        return f"<span>{obj.domain} · {obj.holding_company or '—'}</span>"


class NetworkView(_Override, ModelView):
    fields = ["id", "name", "phase", "status", "signup_url", "login_url"]


class NetworkApplicationView(_Override, ModelView):
    fields = ["id", "site", "network_name", "status", "publisher_id",
              "submission_date", "next_followup_date", "rejection_reason"]
    label = "Network Applications"


class WorkflowView(_RO, ModelView):
    fields = ["id", "site_domain", "network_name", "kind", "state", "created_by", "created_at"]


class AuditView(_RO, ModelView):
    fields = ["id", "actor_kind", "actor", "action", "target", "created_at"]


class NetworkCredentialView(_RO, ModelView):
    fields = ["id", "holding_company", "network", "username"]  # password_enc omitted


class SiteSecretView(_RO, ModelView):
    fields = ["id", "site", "field"]  # value_enc omitted; site shows domain + holding co
    label = "Site Secrets"


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
    admin.add_view(SiteView(Site))
    admin.add_view(NetworkView(Network))
    admin.add_view(NetworkApplicationView(NetworkApplication))
    admin.add_view(WorkflowView(WorkflowRun))
    admin.add_view(AuditView(AuditLog))
    admin.add_view(NetworkCredentialView(NetworkCredential))
    admin.add_view(SiteSecretView(SiteSecret))
    admin.add_view(UserView(User))
    admin.mount_to(app)
