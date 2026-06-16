import time
from app.database import get_db
from app.models.tax_job import TaxJob

def process_tax_job_task(job_id: int):
    """Core task stub to process tax jobs in the background queue."""
    print(f"[Worker] Starting background processing for tax job ID: {job_id}")
    
    with get_db() as db:
        # Fetch the job
        job = db.query(TaxJob).filter(TaxJob.id == job_id).first()
        if not job:
            print(f"[Worker] Error: Tax job ID {job_id} not found in database!")
            return

        # 1. Update status to 'PROCESSING'
        job.status = TaxJob.STATUS_PROCESSING
        db.commit()
        print(f"[Worker] Job ID {job_id} status flipped to PROCESSING. Starting mock extraction work...")

    # 2. Simulate heavy file extraction and anomaly checking work
    time.sleep(5)

    with get_db() as db:
        job = db.query(TaxJob).filter(TaxJob.id == job_id).first()
        if not job:
            print(f"[Worker] Error: Tax job ID {job_id} not found during completion!")
            return

        # 3. Flip status to 'REVIEW_NEEDED'
        job.status = TaxJob.STATUS_REVIEW_NEEDED
        db.commit()
        print(f"[Worker] Job ID {job_id} status flipped to REVIEW_NEEDED. Background task complete.")
