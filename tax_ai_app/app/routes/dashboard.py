from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db_session
from app.models.tax_job import TaxJob
from app.models.checklist_item import ChecklistItem
from app.routes.auth import get_current_user_from_cookie

router = APIRouter(tags=["Dashboard"])
templates = Jinja2Templates(directory="templates")

@router.get("/dashboard", response_class=HTMLResponse)
def get_dashboard(request: Request, db: Session = Depends(get_db_session)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    # Fetch all tax jobs, ordered by newest first
    jobs = db.query(TaxJob).order_by(TaxJob.created_at.desc()).all()
    
    # Calculate open missing document items for each job
    enriched_jobs = []
    for job in jobs:
        missing_count = db.query(ChecklistItem).filter(
            ChecklistItem.tax_job_id == job.id,
            ChecklistItem.type == ChecklistItem.TYPE_MISSING_DOCUMENT,
            ChecklistItem.status == ChecklistItem.STATUS_OPEN
        ).count()
        
        enriched_jobs.append({
            "id": job.id,
            "client_name": job.client_name,
            "client_email": job.client_email,
            "tax_year": job.tax_year,
            "return_type": job.return_type,
            "status": job.status,
            "missing_count": missing_count,
            "created_at": job.created_at
        })

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "user": user,
            "jobs": enriched_jobs
        }
    )
