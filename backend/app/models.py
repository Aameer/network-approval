"""C3 data model — the greenfield network-approval state C3 owns.

C3 is the source of truth for approval *workflow* state; GCMS stays the authority
on site/product truth (read via GraphQL). See the build plan.
"""
from datetime import date, datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


class ApplicationStatus(str, Enum):
    not_applied = "not_applied"
    applied = "applied"
    awaiting = "awaiting"
    approved = "approved"
    rejected = "rejected"
    re_applied = "re_applied"


class Site(SQLModel, table=True):
    """A property in the portfolio registry (seeded from the inventory sheet)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    domain: str = Field(index=True, unique=True)
    holding_company: Optional[str] = None   # the MCC / holding co — one inbox + vault per company
    site_category: Optional[str] = None
    website_status: Optional[str] = None
    repo: Optional[str] = None
    vercel_project: Optional[str] = None
    ga4_property_id: Optional[str] = None
    # --- richer registry fields ingested from the inventory sheet (secrets excluded) ---
    persona: Optional[str] = None
    country: Optional[str] = None
    mcc_id: Optional[str] = None
    mcc_admin_email: Optional[str] = None
    website_type: Optional[str] = None
    redirection_status: Optional[str] = None
    clickout_moved: Optional[str] = None
    wct_user_website_id: Optional[str] = None
    gtm_tag: Optional[str] = None
    registered_on: Optional[str] = None
    domain_expiry: Optional[str] = None
    privacy_protection: Optional[str] = None
    repo_link: Optional[str] = None
    repo_criticality: Optional[str] = None
    repo_status: Optional[str] = None
    raw: Optional[str] = None                # full non-secret row as JSON (nothing lost)
    phase: int = 0                          # 0..3 playbook phase
    is_sandbox: bool = False
    notes: Optional[str] = None

    def __str__(self) -> str:               # how a Site renders in admin relationships
        return f"{self.domain} · {self.holding_company or '—'}"


class NetworkApplication(SQLModel, table=True):
    """One (site x affiliate-network) application lifecycle — C3 owns this."""
    id: Optional[int] = Field(default=None, primary_key=True)
    site_id: int = Field(foreign_key="site.id", index=True)
    network_name: str
    status: ApplicationStatus = Field(default=ApplicationStatus.not_applied)
    publisher_id: Optional[str] = None       # settled outcome (services pull this from C3)
    credentials_ref: Optional[str] = None    # vault pointer, never the secret
    submission_date: Optional[date] = None
    response_date: Optional[date] = None
    next_followup_date: Optional[date] = None
    rejection_reason: Optional[str] = None
    notes: Optional[str] = None
    site: Optional["Site"] = Relationship()   # for admin display (site domain + holding co)


class WorkflowRun(SQLModel, table=True):
    """A durable run of a gated action (apply, parse-inbox, ...)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    site_domain: str
    network_name: Optional[str] = None
    kind: str                                # apply / parse_inbox / milestone
    state: str = "created"                   # created/dry_run/awaiting_approval/running/done/failed
    dry_run_plan: Optional[str] = None       # JSON string
    created_by: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AuditLog(SQLModel, table=True):
    """Every act crosses the policy boundary and lands here — attributable, timestamped."""
    id: Optional[int] = Field(default=None, primary_key=True)
    actor: str                               # user email or agent name
    actor_kind: str = "human"                # human / agent / system
    action: str
    target: Optional[str] = None
    detail: Optional[str] = None             # JSON
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SiteSecret(SQLModel, table=True):
    """Encrypted secret value for a site (mcc password, payment card/link).
    Value is Fernet-ciphertext — never plaintext. Admin-only to read, audited."""
    id: Optional[int] = Field(default=None, primary_key=True)
    site_id: int = Field(foreign_key="site.id", index=True)
    field: str
    value_enc: str
    site: Optional["Site"] = Relationship()   # for admin display (which site)


class NetworkCredential(SQLModel, table=True):
    """A network account login (per holding-company x network), password encrypted.
    Leased by the apply agent at submit time — never plaintext in code/DB/prompts."""
    id: Optional[int] = Field(default=None, primary_key=True)
    holding_company: str = Field(index=True)
    network: str = Field(index=True)
    username: str
    password_enc: str
    notes: Optional[str] = None


class Network(SQLModel, table=True):
    """Affiliate-network registry — signup/login URLs discovered once, reused everywhere."""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    phase: int = 1
    signup_url: Optional[str] = None
    login_url: Optional[str] = None
    status: str = "unverified"   # unverified / pending / verified
    notes: Optional[str] = None


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    name: Optional[str] = None
    role: str = "operator"
    created_at: datetime = Field(default_factory=datetime.utcnow)
