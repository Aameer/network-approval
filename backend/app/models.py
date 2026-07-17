"""C3 data model — the greenfield network-approval state C3 owns.

C3 is the source of truth for approval *workflow* state; GCMS stays the authority
on site/product truth (read via GraphQL). See the build plan.
"""
from datetime import date, datetime
from enum import Enum
from typing import List, Optional

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

    def __admin_repr__(self, request) -> str:   # starlette-admin: label for the related-site chip
        return f"{self.domain} · {self.holding_company or '—'}"

    def __admin_select2_repr__(self, request) -> str:
        return f'<span>{self.domain} · {self.holding_company or "—"}</span>'


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
    """A durable run of a gated action (discover, apply, parse-inbox, ...)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    site_domain: str
    network_name: Optional[str] = None
    kind: str                                # discover / apply / approval_flip / parse_inbox
    operation: Optional[str] = None          # create / update — reconcile mode for apply runs
    state: str = "created"                   # created/dry_run/awaiting_approval/running/done/failed
    dry_run_plan: Optional[str] = None       # JSON: the inputs that WILL be entered (incl. Skyvern task)
    result: Optional[str] = None             # JSON: the outcome (success/failure, run_id, error)
    created_by: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    answers: List["RunAnswer"] = Relationship(back_populates="run")

    def __str__(self) -> str:
        return f"#{self.id} {self.site_domain}·{self.network_name} ({self.operation or self.kind})"

    def __admin_repr__(self, request) -> str:
        return f"#{self.id} {self.site_domain} · {self.network_name} ({self.operation or self.kind})"

    def __admin_select2_repr__(self, request) -> str:
        return (f'<span>#{self.id} {self.site_domain} · {self.network_name} '
                f'({self.operation or self.kind})</span>')

    @property
    def review_url(self) -> str:
        """Deep link to the single-page review for this run (opens in the admin shell)."""
        return f"/review/{self.id}"

    @property
    def skyvern_url(self) -> str:
        """Link to the Skyvern run (live browser view, recording, step logs) when this run
        executed/scouted via Skyvern. Empty for runs that never hit the browser."""
        import json
        try:
            rid = json.loads(self.result or "{}").get("run_id")
        except Exception:
            rid = None
        return f"https://app.skyvern.com/tasks/{rid}" if rid else ""


class RunAnswer(SQLModel, table=True):
    """One field of a prepared run's answer sheet — the human-readable, overridable unit.
    `value` is what we'll set (editable = override); `current_value` is what's on the network
    now (update mode). Password answers store only the masked placeholder, never the secret."""
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="workflowrun.id", index=True)
    page: int = 1
    field_key: str
    label: str
    value: Optional[str] = None          # what we'll set — EDITABLE override
    current_value: Optional[str] = None  # what's currently on the network (update mode)
    status: str = "ready"                # ready / MISSING / INVALID / optional-empty
    source: Optional[str] = None
    required: bool = False
    run: Optional["WorkflowRun"] = Relationship(back_populates="answers")

    @property
    def changed(self) -> str:
        """Badge comparing what we'll submit vs what's live on the network:
        '⚠ changed' (differs), '✓ same' (matches), '—' (we submit nothing for this field)."""
        if self.field_key in ("password", "password_confirm"):
            return "—"
        a = str(self.value or "").strip()
        if not a:
            return "—"  # nothing to submit -> nothing changes
        b = str(self.current_value or "").strip()
        return "✓ same" if a == b else "⚠ changed"


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

    @property
    def value(self) -> str:
        """Decrypted plaintext — surfaced ONLY in the password-gated admin detail view."""
        from .services import vault
        try:
            return vault.decrypt(self.value_enc)
        except Exception:
            return "(unable to decrypt)"

    @value.setter
    def value(self, plaintext: str) -> None:
        """Admin override — encrypt the new plaintext back into value_enc (never store plaintext)."""
        from .services import vault
        if plaintext is not None and not str(plaintext).startswith("(unable to decrypt"):
            self.value_enc = vault.encrypt(str(plaintext))


class NetworkCredential(SQLModel, table=True):
    """A network account login (per holding-company x network), password encrypted.
    Leased by the apply agent at submit time — never plaintext in code/DB/prompts."""
    id: Optional[int] = Field(default=None, primary_key=True)
    holding_company: str = Field(index=True)
    network: str = Field(index=True)
    username: str
    password_enc: str
    notes: Optional[str] = None

    @property
    def password(self) -> str:
        """Decrypted login password — surfaced ONLY in the password-gated admin detail view."""
        from .services import vault
        try:
            return vault.decrypt(self.password_enc)
        except Exception:
            return "(unable to decrypt)"

    @password.setter
    def password(self, plaintext: str) -> None:
        """Admin override — encrypt the new plaintext back into password_enc."""
        from .services import vault
        if plaintext is not None and not str(plaintext).startswith("(unable to decrypt"):
            self.password_enc = vault.encrypt(str(plaintext))


class Network(SQLModel, table=True):
    """Affiliate-network registry — signup/login URLs discovered once, reused everywhere."""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    phase: int = 1
    signup_url: Optional[str] = None
    login_url: Optional[str] = None
    profile_url: Optional[str] = None            # account profile/settings page (for update runs)
    status: str = "unverified"   # unverified / pending / verified
    form_schema: Optional[str] = None            # JSON: fields the Discover run mapped (label/type/required/options)
    form_schema_at: Optional[datetime] = None    # when the schema was last discovered
    notes: Optional[str] = None


class BillingProfile(SQLModel, table=True):
    """The complete, real account profile for a holding company — everything a network
    signup/settings form can ask for. Filled ONCE by ops, reused for every apply/update.
    The Prepare run answers each discovered form field from here; nothing is ever invented."""
    id: Optional[int] = Field(default=None, primary_key=True)
    holding_company: str = Field(index=True, unique=True)
    company_name: Optional[str] = None
    contact_name: Optional[str] = None           # contact / billing person name
    contact_email: Optional[str] = None
    phone: Optional[str] = None
    address1: Optional[str] = None
    address2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None
    paypal_email: Optional[str] = None           # payout destination — MUST be real
    tax_id: Optional[str] = None
    extra: Optional[str] = None                  # JSON: any network-specific answers
    notes: Optional[str] = None


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    name: Optional[str] = None
    role: str = "operator"
    created_at: datetime = Field(default_factory=datetime.utcnow)
