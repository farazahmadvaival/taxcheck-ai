from fastapi import APIRouter, Depends, Request, status, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db_session
from app.models.checklist_item import ChecklistItem
from app.models.tax_job import TaxJob
from app.routes.auth import get_current_user_from_cookie

router = APIRouter(prefix="/checklist-items", tags=["Checklist"])

def check_and_update_job_status(job_id: int, db: Session):
    # Fetch all open checklist items for this job
    open_items_count = db.query(ChecklistItem).filter(
        ChecklistItem.tax_job_id == job_id,
        ChecklistItem.status == ChecklistItem.STATUS_OPEN
    ).count()
    
    # Fetch the job
    job = db.query(TaxJob).filter(TaxJob.id == job_id).first()
    if job:
        if open_items_count == 0:
            # If no open items left, and it was REVIEW_NEEDED or PROCESSING, flip to COMPLETED
            if job.status in [TaxJob.STATUS_REVIEW_NEEDED, TaxJob.STATUS_PROCESSING]:
                job.status = TaxJob.STATUS_COMPLETED
        else:
            # If there are open items left, and it was COMPLETED, flip back to REVIEW_NEEDED
            if job.status == TaxJob.STATUS_COMPLETED:
                job.status = TaxJob.STATUS_REVIEW_NEEDED
        db.commit()

@router.patch("/{id}")
@router.post("/{id}")
async def update_checklist_item_status(
    id: int,
    request: Request,
    db: Session = Depends(get_db_session)
):
    user = get_current_user_from_cookie(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    # Read body (JSON, Form or Query)
    new_status = None
    content_type = request.headers.get("content-type", "")
    
    if "application/json" in content_type:
        try:
            body = await request.json()
            new_status = body.get("status")
        except Exception:
            pass
    else:
        try:
            form = await request.form()
            new_status = form.get("status")
        except Exception:
            pass
            
    # Check query params if not found in body
    if not new_status:
        new_status = request.query_params.get("status")
        
    if not new_status:
        raise HTTPException(status_code=400, detail="Missing status parameter")
        
    # Validate status value
    new_status = new_status.upper()
    valid_statuses = [
        ChecklistItem.STATUS_OPEN,
        ChecklistItem.STATUS_APPROVED,
        ChecklistItem.STATUS_IGNORED,
        ChecklistItem.STATUS_RESOLVED
    ]
    if new_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status: {new_status}")
        
    # Fetch and update checklist item
    item = db.query(ChecklistItem).filter(ChecklistItem.id == id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Checklist item not found")
        
    item.status = new_status
    db.commit()
    
    # Sync job status
    check_and_update_job_status(item.tax_job_id, db)
    
    return {
        "success": True,
        "id": item.id,
        "status": item.status
    }
