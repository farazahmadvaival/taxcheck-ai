import time
import os
import traceback
from app.database import get_db
from app.models.tax_job import TaxJob
from app.models.upload_round import UploadRound
from app.models.processing_log import ProcessingLog
from app.services.zip_service import extract_zip
from app.services.file_inventory_service import build_file_inventory

def process_tax_job_task(job_id: int):
    """Core task loop to process tax jobs in the background queue."""
    print(f"[Worker] Starting background processing for tax job ID: {job_id}")
    
    with get_db() as db:
        # Fetch the job
        job = db.query(TaxJob).filter(TaxJob.id == job_id).first()
        if not job:
            print(f"[Worker] Error: Tax job ID {job_id} not found in database!")
            return

        # 1. Update status to 'PROCESSING'
        job.status = TaxJob.STATUS_PROCESSING
        
        # Log startup progress
        start_log = ProcessingLog(
            tax_job_id=job_id,
            level=ProcessingLog.LEVEL_INFO,
            message="Starting extraction and file inventory analysis..."
        )
        db.add(start_log)
        db.commit()
        print(f"[Worker] Job ID {job_id} status updated to PROCESSING.")

    # 2. Fetch the initial upload round and run processing
    try:
        with get_db() as db:
            round_record = db.query(UploadRound).filter(
                UploadRound.tax_job_id == job_id,
                UploadRound.upload_type == UploadRound.TYPE_INITIAL
            ).first()
            
            if not round_record:
                raise ValueError("Initial upload round record not found in database!")

            zip_path = round_record.zip_path
            extracted_dir = os.path.join("storage", "jobs", str(job_id), "extracted")

            # A. Safe ZIP extraction
            extract_zip(zip_path, extracted_dir)

            # B. Index files into DB inventory
            build_file_inventory(job_id, round_record.id, extracted_dir, db)

        # 3. Simulate analysis processing phase (e.g. OCR, rules engine)
        time.sleep(5)

        with get_db() as db:
            job = db.query(TaxJob).filter(TaxJob.id == job_id).first()
            if not job:
                raise ValueError("Tax job record disappeared during processing!")

            # Flip status to 'REVIEW_NEEDED'
            job.status = TaxJob.STATUS_REVIEW_NEEDED
            db.commit()
            print(f"[Worker] Job ID {job_id} successfully processed. Status: REVIEW_NEEDED.")
            
    except Exception as e:
        # Error handling: Log traceback details and fail the job status
        error_msg = f"Task execution failed: {str(e)}\n{traceback.format_exc()}"
        print(f"[Worker] Error during job {job_id} processing: {error_msg}")
        
        with get_db() as db:
            job = db.query(TaxJob).filter(TaxJob.id == job_id).first()
            if job:
                job.status = TaxJob.STATUS_FAILED
                
            error_log = ProcessingLog(
                tax_job_id=job_id,
                level=ProcessingLog.LEVEL_ERROR,
                message=f"Critical processing error: {str(e)}"
            )
            db.add(error_log)
            db.commit()
