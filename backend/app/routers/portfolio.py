"""Portfolio registry read endpoints (the dashboard reads these)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db import get_session
from ..models import NetworkApplication, Site

router = APIRouter(prefix="/api", tags=["portfolio"])


@router.get("/portfolio")
def portfolio(sandbox: bool = False, session: Session = Depends(get_session)):
    q = select(Site)
    if sandbox:
        q = q.where(Site.is_sandbox == True)  # noqa: E712
    sites = session.exec(q.order_by(Site.is_sandbox.desc(), Site.domain)).all()

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
            "is_sandbox": site.is_sandbox,
            "networks": [
                {"network": a.network_name, "status": a.status, "publisher_id": a.publisher_id}
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
