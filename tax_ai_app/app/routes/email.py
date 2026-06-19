from fastapi import APIRouter, Depends, Request, Form, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime

from app.database import get_db_session
from app.models.tax_job import TaxJob
from app.models.checklist_item import ChecklistItem
from app.models.email_request import EmailRequest
from app.routes.auth import get_current_user_from_cookie
from app.services.llm_service import generate_email_draft
from app.services.email_service import send_email

router = APIRouter(tags=["Email"])
templates = Jinja2Templates(directory="templates")

@router.get("/jobs/{id}/email", response_class=HTMLResponse)
def get_email_review(id: int, request: Request, db: Session = Depends(get_db_session)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    # Fetch the job
    job = db.query(TaxJob).filter(TaxJob.id == id).first()
    if not job:
        return RedirectResponse(
            url="/dashboard?error=Tax+job+not+found",
            status_code=status.HTTP_303_SEE_OTHER
        )

    # Fetch only APPROVED checklist items for this job
    approved_items = db.query(ChecklistItem).filter(
        ChecklistItem.tax_job_id == id,
        ChecklistItem.status == ChecklistItem.STATUS_APPROVED
    ).all()

    if not approved_items:
        return RedirectResponse(
            url=f"/jobs/{id}?error=No+approved+checklist+items.+Please+approve+at+least+one+item.",
            status_code=status.HTTP_303_SEE_OTHER
        )

    # Convert items to clean JSON payload for LLM service
    approved_payload = [
        {
            "title": item.title,
            "description": item.description,
            "recommended_document": item.recommended_document
        }
        for item in approved_items
    ]

    # Generate draft using Gemini Flash via llm_service
    subject, body = generate_email_draft(job.client_name, approved_payload)

    # Check if a DRAFT email record already exists for this job
    email_record = db.query(EmailRequest).filter(
        EmailRequest.tax_job_id == id,
        EmailRequest.status == EmailRequest.STATUS_DRAFT
    ).first()

    if email_record:
        # Update existing draft
        email_record.email_to = job.client_email
        email_record.subject = subject
        email_record.body = body
    else:
        # Create a new draft
        email_record = EmailRequest(
            tax_job_id=id,
            email_to=job.client_email,
            subject=subject,
            body=body,
            status=EmailRequest.STATUS_DRAFT
        )
        db.add(email_record)

    db.commit()
    db.refresh(email_record)

    return templates.TemplateResponse(
        request=request,
        name="email_review.html",
        context={
            "user": user,
            "job": job,
            "email_record": email_record,
            "approved_items": approved_items
        }
    )

@router.post("/jobs/{id}/email/send")
def send_client_email(
    id: int,
    request: Request,
    subject: str = Form(...),
    body: str = Form(...),
    db: Session = Depends(get_db_session)
):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    # Fetch the job
    job = db.query(TaxJob).filter(TaxJob.id == id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Tax job not found")

    # Fetch the DRAFT email record
    email_record = db.query(EmailRequest).filter(
        EmailRequest.tax_job_id == id,
        EmailRequest.status == EmailRequest.STATUS_DRAFT
    ).first()

    if not email_record:
        raise HTTPException(status_code=404, detail="No email draft found to send")

    # Update record with edited values
    email_record.subject = subject
    email_record.body = body

    # Call the email service to send the message
    success = send_email(job.client_email, subject, body)

    if success:
        email_record.status = EmailRequest.STATUS_SENT
        email_record.sent_at = datetime.utcnow()
        email_record.approved_by = user.id
        
        # Update job status to WAITING_CLIENT_DOCUMENTS
        job.status = TaxJob.STATUS_WAITING_CLIENT_DOCUMENTS
        db.commit()
        
        # Log info message to processing_logs
        from app.models.processing_log import ProcessingLog
        db.add(ProcessingLog(
            tax_job_id=id,
            level=ProcessingLog.LEVEL_INFO,
            message=f"Outstanding document request email sent to: {job.client_email}"
        ))
        db.commit()

        return RedirectResponse(
            url=f"/jobs/{id}?success=Email+sent+successfully",
            status_code=status.HTTP_303_SEE_OTHER
        )
    else:
        email_record.status = EmailRequest.STATUS_FAILED
        db.commit()
        return RedirectResponse(
            url=f"/jobs/{id}/email?error=Failed+to+transmit+email+message",
            status_code=status.HTTP_303_SEE_OTHER
        )
