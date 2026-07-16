"""SQLAdmin data browser — read-only, password-gated, encrypted columns never shown.

Mounted at /admin on the FastAPI app. A real admin framework (auth backend, list/detail/
search/pagination) instead of a hand-rolled view. Everything read-only for safety.
"""
from __future__ import annotations

from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend

from .config import ADMIN_PANEL_PASSWORD, SESSION_SECRET
from .db import engine
from .models import (
    AuditLog, Network, NetworkApplication, NetworkCredential, Site, SiteSecret,
    User, WorkflowRun,
)


class AdminAuth(AuthenticationBackend):
    async def login(self, request):
        form = await request.form()
        if ADMIN_PANEL_PASSWORD and form.get("password") == ADMIN_PANEL_PASSWORD:
            request.session["admin_panel"] = True
            return True
        return False

    async def logout(self, request):
        request.session.pop("admin_panel", None)
        return True

    async def authenticate(self, request):
        return bool(request.session.get("admin_panel"))


class _RO:
    can_create = False
    can_edit = False
    can_delete = False
    can_export = False


class SiteAdmin(_RO, ModelView, model=Site):
    column_list = [Site.id, Site.domain, Site.holding_company, Site.phase,
                   Site.website_status, Site.country, Site.redirection_status, Site.is_sandbox]
    column_searchable_list = [Site.domain, Site.holding_company]


class NetworkAdmin(_RO, ModelView, model=Network):
    column_list = [Network.id, Network.name, Network.phase, Network.status,
                   Network.signup_url, Network.login_url]


class NetworkApplicationAdmin(_RO, ModelView, model=NetworkApplication):
    column_list = [NetworkApplication.id, NetworkApplication.site_id, NetworkApplication.network_name,
                   NetworkApplication.status, NetworkApplication.publisher_id,
                   NetworkApplication.submission_date, NetworkApplication.next_followup_date]


class WorkflowAdmin(_RO, ModelView, model=WorkflowRun):
    column_list = [WorkflowRun.id, WorkflowRun.site_domain, WorkflowRun.network_name,
                   WorkflowRun.kind, WorkflowRun.state, WorkflowRun.created_by, WorkflowRun.created_at]


class AuditAdmin(_RO, ModelView, model=AuditLog):
    column_list = [AuditLog.id, AuditLog.actor_kind, AuditLog.actor, AuditLog.action,
                   AuditLog.target, AuditLog.created_at]


class NetworkCredentialAdmin(_RO, ModelView, model=NetworkCredential):
    # password_enc excluded from list AND detail — the ciphertext never surfaces here.
    column_list = [NetworkCredential.id, NetworkCredential.holding_company,
                   NetworkCredential.network, NetworkCredential.username]
    column_details_list = column_list


class SiteSecretAdmin(_RO, ModelView, model=SiteSecret):
    # value_enc excluded.
    column_list = [SiteSecret.id, SiteSecret.site_id, SiteSecret.field]
    column_details_list = column_list


class UserAdmin(_RO, ModelView, model=User):
    column_list = [User.id, User.email, User.name, User.role, User.created_at]


def setup_admin(app):
    if not ADMIN_PANEL_PASSWORD:
        return  # panel stays off until a password is configured
    admin = Admin(app, engine, authentication_backend=AdminAuth(secret_key=SESSION_SECRET),
                  title="C3 Admin")
    for view in (SiteAdmin, NetworkAdmin, NetworkApplicationAdmin, WorkflowAdmin,
                 AuditAdmin, NetworkCredentialAdmin, SiteSecretAdmin, UserAdmin):
        admin.add_view(view)
