"""Portfolio registry read endpoints (the dashboard reads these)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db import get_session
from ..models import NetworkApplication, Site
from ..services import vault

router = APIRouter(prefix="/api", tags=["portfolio"])


@router.get("/portfolio")
def portfolio(sandbox: bool = False, session: Session = Depends(get_session)):
    q = select(Site)
    if sandbox:
        q = q.where(Site.is_sandbox == True)  # noqa: E712
    sites = session.exec(q.order_by(Site.is_sandbox.desc(), Site.domain)).all()
    secret_ids = vault.sites_with_secrets()

    out = []
    for site in sites:
        apps = session.exec(
            select(NetworkApplication).where(NetworkApplication.site_id == site.id)
        ).all()
        out.append({
            "domain": site.domain,
            "holding_company": site.holding_company,
            "phase": site.phase,
            "category": site.site_category,
            "status": site.website_status,
            "country": site.country,
            "website_type": site.website_type,
            "redirection": site.redirection_status,
            "clickout_moved": site.clickout_moved,
            "mcc_id": site.mcc_id,
            "ga4_property_id": site.ga4_property_id,
            "has_secrets": site.id in secret_ids,
            "is_sandbox": site.is_sandbox,
            "networks": [
                {"id": a.id, "network": a.network_name, "status": a.status.value, "publisher_id": a.publisher_id}
                for a in apps
            ],
        })
    return {"count": len(out), "sites": out}


@router.get("/sites/{domain}")
def site_detail(domain: str, session: Session = Depends(get_session)):
    site = session.exec(select(Site).where(Site.domain == domain)).first()
    if not site:
        raise HTTPException(status_code=404, detail="site not found")
    apps = session.exec(
        select(NetworkApplication).where(NetworkApplication.site_id == site.id)
    ).all()
    return {"site": site, "networks": apps}
