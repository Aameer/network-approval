"""Background-job control — manual trigger for the demo (scheduler runs them on a timer)."""
from fastapi import APIRouter, HTTPException, Request

from ..services import jobs

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("/run")
def run(request: Request):
    if not request.session.get("user"):
        raise HTTPException(status_code=401, detail="sign in")
    return jobs.run_all()
