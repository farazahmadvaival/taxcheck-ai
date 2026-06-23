import time
import os
import traceback
from app.database import get_db
from app.models.tax_job import TaxJob
from app.models.upload_round import UploadRound
from app.models.job_file import JobFile
from app.models.processing_log import ProcessingLog
from app.models.checklist_item import ChecklistItem
from app.services.zip_service import extract_zip
from app.services.file_inventory_service import build_file_inventory
from app.services.ocr_service import route_and_extract

def match_document_type_to_checklist_item(doc_type: str, item) -> bool:
    doc_type_upper = doc_type.upper()
    title_lower = (item.title or "").lower()
    rec_lower = (item.recommended_document or "").lower()
    
    if doc_type_upper == "PRIOR_YEAR_RETURN":
        return "prior year" in title_lower or "prior year" in rec_lower
    elif doc_type_upper == "BALANCE_SHEET":
        return "balance sheet" in title_lower or "balance sheet" in rec_lower
    elif doc_type_upper == "INCOME_STATEMENT":
        return "income statement" in title_lower or "p&l" in title_lower or "profit & loss" in title_lower or "income statement" in rec_lower
    elif doc_type_upper == "TRIAL_BALANCE":
        return "trial balance" in title_lower or "trial balance" in rec_lower
    elif doc_type_upper == "GENERAL_LEDGER":
        return "general ledger" in title_lower or "general ledger" in rec_lower
    elif doc_type_upper in ["PAYROLL_SUMMARY", "W2_W3"]:
        return "payroll" in title_lower or "payroll" in rec_lower or "w-2" in rec_lower or "w-3" in rec_lower
    elif doc_type_upper == "DEPRECIATION_SCHEDULE":
        return "depreciation" in title_lower or "depreciation" in rec_lower
    elif doc_type_upper == "LOAN_STATEMENT":
        return "loan" in title_lower or "loan" in rec_lower
    elif doc_type_upper == "BANK_STATEMENT":
        return "bank" in title_lower or "bank" in rec_lower
    elif doc_type_upper == "AR_AGING":
        return "accounts receivable" in title_lower or "ar aging" in title_lower or "ar aging" in rec_lower or "accounts receivable" in rec_lower
    elif doc_type_upper == "AP_AGING":
        return "accounts payable" in title_lower or "ap aging" in title_lower or "ap aging" in rec_lower or "accounts payable" in rec_lower
    elif doc_type_upper == "SHAREHOLDER_DISTRIBUTION":
        return "shareholder distribution" in title_lower or "owner draw" in title_lower or "shareholder distribution" in rec_lower
    
    return False

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

    try:
        # 2. Fetch all unprocessed upload rounds for this job
        with get_db() as db:
            unprocessed_rounds = db.query(UploadRound).filter(
                UploadRound.tax_job_id == job_id,
                UploadRound.status != "PROCESSED"
            ).order_by(UploadRound.round_number).all()

        is_additional_round = False
        processed_round_ids = []
        
        if not unprocessed_rounds:
            print(f"[Worker] No unprocessed upload rounds found for job ID: {job_id}")
        
        for round_record in unprocessed_rounds:
            processed_round_ids.append(round_record.id)
            if round_record.upload_type == UploadRound.TYPE_MISSING_DOCUMENTS:
                is_additional_round = True
                
            print(f"[Worker] Processing upload round {round_record.round_number} (ID: {round_record.id}, Type: {round_record.upload_type})")
            
            # Update round status to PROCESSING
            with get_db() as db:
                r = db.query(UploadRound).filter(UploadRound.id == round_record.id).first()
                if r:
                    r.status = "PROCESSING"
                    db.commit()

            zip_path = round_record.zip_path
            # Keep extraction directory clean and round-isolated
            extracted_dir = os.path.join("storage", "jobs", str(job_id), "extracted", f"round_{round_record.id}")

            # A. Safe ZIP extraction
            extract_zip(zip_path, extracted_dir)

            # B. Index files into DB inventory
            with get_db() as db:
                build_file_inventory(job_id, round_record.id, extracted_dir, db)

            # C. Read the indexed files and process through the routing engine
            with get_db() as db:
                # Query only files associated with this upload round
                round_files = db.query(JobFile).filter(
                    JobFile.tax_job_id == job_id,
                    JobFile.upload_round_id == round_record.id
                ).all()
                print(f"[Worker] Found {len(round_files)} files in round {round_record.round_number} to parse.")

                parsed_count = 0
                unsupported_count = 0

                for file_record in round_files:
                    # Resolve full path to file
                    physical_file_path = os.path.join(os.getcwd(), file_record.file_path)
                    print(f"[Worker] Processing file: {file_record.file_name}")

                    try:
                        # Run the unified extraction router
                        text, method, score, page_count, success = route_and_extract(
                            physical_file_path, job_id, db
                        )
                        
                        file_record.extraction_method = method
                        file_record.confidence_score = score
                        file_record.page_count = page_count

                        if success and method not in ["UNSUPPORTED", "FAILED"]:
                            # Save extracted text representation next to it on local disk
                            txt_path = physical_file_path + ".txt"
                            with open(txt_path, "w", encoding="utf-8") as f:
                                f.write(text)

                            file_record.is_processed = True
                            parsed_count += 1
                        else:
                            file_record.is_processed = False
                            unsupported_count += 1
                            
                    except Exception as file_parse_err:
                        print(f"[Worker] Failed to parse file {file_record.file_name}: {file_parse_err}")
                        file_record.extraction_method = "FAILED"
                        file_record.is_processed = False
                        
                        err_log = ProcessingLog(
                            tax_job_id=job_id,
                            level=ProcessingLog.LEVEL_WARNING,
                            message=f"Failed to parse file {file_record.file_name}: {str(file_parse_err)}"
                        )
                        db.add(err_log)

                # Mark round as PROCESSED
                r = db.query(UploadRound).filter(UploadRound.id == round_record.id).first()
                if r:
                    r.status = "PROCESSED"
                
                # Log parsing outcome summary for this round
                parsing_summary_log = ProcessingLog(
                    tax_job_id=job_id,
                    level=ProcessingLog.LEVEL_INFO,
                    message=f"Round {round_record.round_number} extraction complete. Parsed: {parsed_count} files. Unprocessed/unsupported: {unsupported_count} files."
                )
                db.add(parsing_summary_log)
                db.commit()

        # 4. Classification Phase
        with get_db() as db:
            from app.services.document_classifier import run_classification_phase
            if is_additional_round:
                run_classification_phase(job_id, db, round_ids=processed_round_ids)
            else:
                run_classification_phase(job_id, db)

        # 5. Anomaly Check / Matching Phase
        with get_db() as db:
            if is_additional_round:
                # Run matching loop: if a newly uploaded file matches the document type of an outstanding checklist item, resolve it
                outstanding_items = db.query(ChecklistItem).filter(
                    ChecklistItem.tax_job_id == job_id,
                    ChecklistItem.status.in_([ChecklistItem.STATUS_OPEN, ChecklistItem.STATUS_APPROVED])
                ).all()
                
                new_files = db.query(JobFile).filter(
                    JobFile.tax_job_id == job_id,
                    JobFile.upload_round_id.in_(processed_round_ids)
                ).all()
                
                print(f"[Worker] Running matching loop: {len(new_files)} new files, {len(outstanding_items)} outstanding items.")
                
                resolved_count = 0
                for file_record in new_files:
                    doc_type = file_record.detected_document_type
                    if not doc_type:
                        continue
                    
                    for item in outstanding_items:
                        if match_document_type_to_checklist_item(doc_type, item):
                            print(f"[Worker] Auto-resolving item '{item.title}' (ID: {item.id}) because {doc_type} was uploaded.")
                            item.status = ChecklistItem.STATUS_RESOLVED
                            resolved_count += 1
                            
                db.commit()
                if resolved_count > 0:
                    db.add(ProcessingLog(
                        tax_job_id=job_id,
                        level=ProcessingLog.LEVEL_INFO,
                        message=f"Additional documents matching resolved {resolved_count} checklist items."
                    ))
                    db.commit()
            else:
                from app.services.anomaly_engine import run_anomaly_rules
                run_anomaly_rules(job_id, db)

        # 6. Final status update
        with get_db() as db:
            job = db.query(TaxJob).filter(TaxJob.id == job_id).first()
            if not job:
                raise ValueError("Tax job record disappeared during processing!")

            if is_additional_round:
                # Check if all high-priority missing document items are resolved (no longer OPEN or APPROVED)
                open_high_missing_count = db.query(ChecklistItem).filter(
                    ChecklistItem.tax_job_id == job_id,
                    ChecklistItem.type == ChecklistItem.TYPE_MISSING_DOCUMENT,
                    ChecklistItem.severity == ChecklistItem.SEVERITY_HIGH,
                    ChecklistItem.status.in_([ChecklistItem.STATUS_OPEN, ChecklistItem.STATUS_APPROVED])
                ).count()
                
                if open_high_missing_count == 0:
                    job.status = TaxJob.STATUS_COMPLETED
                    print(f"[Worker] All high-priority missing documents resolved. Job ID {job_id} status: COMPLETED.")
                else:
                    job.status = TaxJob.STATUS_REVIEW_NEEDED
                    print(f"[Worker] Outstanding high-priority missing documents remaining. Job ID {job_id} status: REVIEW_NEEDED.")
            else:
                job.status = TaxJob.STATUS_REVIEW_NEEDED
                print(f"[Worker] Job ID {job_id} successfully processed. Status: REVIEW_NEEDED.")
            
            db.commit()
            
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
                message=f"Critical processing error: {str(e)}\nTraceback:\n{traceback.format_exc()}"
            )
            db.add(error_log)
            db.commit()
