from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import os
import shutil

from app.database import get_db_session
from app.models.tax_job import TaxJob
from app.models.upload_round import UploadRound
from app.routes.auth import get_current_user_from_cookie

router = APIRouter(prefix="/jobs", tags=["Jobs"])
templates = Jinja2Templates(directory="templates")

@router.get("/new", response_class=HTMLResponse)
def get_upload_form(request: Request, error: str | None = None, db: Session = Depends(get_db_session)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="upload_job.html",
        context={"user": user, "error": error}
    )

@router.post("")
def upload_job(
    request: Request,
    client_name: str = Form(...),
    client_email: str = Form(...),
    tax_year: int = Form(...),
    return_type: str = Form(...),
    zip_file: UploadFile = File(...),
    db: Session = Depends(get_db_session)
):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    # 1. Enforce strict .zip extension validation
    if not zip_file.filename.endswith(".zip"):
        return RedirectResponse(
            url="/jobs/new?error=Invalid+file+type.+Please+upload+a+valid+.zip+archive.",
            status_code=status.HTTP_303_SEE_OTHER
        )

    # 2. Write tax_job base record to DB to obtain a unique ID
    new_job = TaxJob(
        client_name=client_name,
        client_email=client_email,
        tax_year=tax_year,
        return_type=return_type,
        status=TaxJob.STATUS_UPLOADED,
        created_by=user.id
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)

    # 3. Create file storage path & write file securely to disk
    job_storage_dir = os.path.join("storage", "jobs", str(new_job.id))
    os.makedirs(job_storage_dir, exist_ok=True)
    file_dest_path = os.path.join(job_storage_dir, "initial.zip")

    try:
        with open(file_dest_path, "wb") as buffer:
            shutil.copyfileobj(zip_file.file, buffer)
    except Exception as e:
        # Roll back database entry if file write failed
        db.delete(new_job)
        db.commit()
        return RedirectResponse(
            url=f"/jobs/new?error=Failed+to+save+uploaded+file:+{str(e)}",
            status_code=status.HTTP_303_SEE_OTHER
        )

    # 4. Generate upload_rounds INITIAL record
    new_round = UploadRound(
        tax_job_id=new_job.id,
        round_number=1,
        upload_type=UploadRound.TYPE_INITIAL,
        zip_path=file_dest_path,
        status=TaxJob.STATUS_UPLOADED
    )
    db.add(new_round)

    # 5. Link file paths back to the main tax_job record
    new_job.uploaded_zip_path = file_dest_path
    db.commit()

    # 6. Enqueue the background processing task and flip status to 'QUEUED'
    from app.services.queue_service import queue
    from app.worker.tasks import process_tax_job_task

    queue.enqueue(process_tax_job_task, new_job.id)
    
    new_job.status = TaxJob.STATUS_QUEUED
    db.commit()

    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/{id}", response_class=HTMLResponse)
def get_job_detail(id: int, request: Request, db: Session = Depends(get_db_session)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    # Fetch the tax job
    job = db.query(TaxJob).filter(TaxJob.id == id).first()
    if not job:
        return RedirectResponse(
            url="/dashboard?error=Tax+job+not+found",
            status_code=status.HTTP_303_SEE_OTHER
        )

    # Fetch files associated with this job
    from app.models.job_file import JobFile
    files = db.query(JobFile).filter(JobFile.tax_job_id == id).order_by(JobFile.created_at.asc()).all()

    # Fetch checklist items associated with this job
    from app.models.checklist_item import ChecklistItem
    checklist_items = db.query(ChecklistItem).filter(ChecklistItem.tax_job_id == id).order_by(ChecklistItem.created_at.asc()).all()

    return templates.TemplateResponse(
        request=request,
        name="job_detail.html",
        context={
            "user": user,
            "job": job,
            "files": files,
            "checklist_items": checklist_items
        }
    )

@router.post("/{id}/additional-documents")
def upload_additional_documents(
    id: int,
    request: Request,
    zip_file: UploadFile = File(...),
    db: Session = Depends(get_db_session)
):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    # Fetch the tax job
    job = db.query(TaxJob).filter(TaxJob.id == id).first()
    if not job:
        return RedirectResponse(
            url="/dashboard?error=Tax+job+not+found",
            status_code=status.HTTP_303_SEE_OTHER
        )

    # 1. Enforce strict .zip extension validation
    if not zip_file.filename.endswith(".zip"):
        return RedirectResponse(
            url=f"/jobs/{id}?error=Invalid+file+type.+Please+upload+a+valid+.zip+archive.",
            status_code=status.HTTP_303_SEE_OTHER
        )

    # 2. Get next round number
    from sqlalchemy import func
    max_round = db.query(func.max(UploadRound.round_number)).filter(UploadRound.tax_job_id == id).scalar() or 0
    next_round_num = max_round + 1

    # 3. Create file storage path & write file securely to disk
    job_storage_dir = os.path.join("storage", "jobs", str(id))
    os.makedirs(job_storage_dir, exist_ok=True)
    file_dest_path = os.path.join(job_storage_dir, f"round_{next_round_num}.zip")

    try:
        with open(file_dest_path, "wb") as buffer:
            shutil.copyfileobj(zip_file.file, buffer)
    except Exception as e:
        return RedirectResponse(
            url=f"/jobs/{id}?error=Failed+to+save+uploaded+file:+{str(e)}",
            status_code=status.HTTP_303_SEE_OTHER
        )

    # 4. Generate upload_rounds MISSING_DOCUMENTS record
    new_round = UploadRound(
        tax_job_id=id,
        round_number=next_round_num,
        upload_type=UploadRound.TYPE_MISSING_DOCUMENTS,
        zip_path=file_dest_path,
        status=TaxJob.STATUS_UPLOADED
    )
    db.add(new_round)
    db.commit()

    # 5. Re-queue the exact same tax_job_id into Redis & flip status to 'REPROCESSING'
    from app.services.queue_service import queue
    from app.worker.tasks import process_tax_job_task

    job.status = TaxJob.STATUS_REPROCESSING
    db.commit()

    queue.enqueue(process_tax_job_task, id)

    return RedirectResponse(
        url=f"/jobs/{id}?success=Additional+documents+uploaded+and+queued+for+processing.",
        status_code=status.HTTP_303_SEE_OTHER
    )
