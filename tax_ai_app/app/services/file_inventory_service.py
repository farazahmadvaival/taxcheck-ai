import os
from sqlalchemy.orm import Session
from app.models.job_file import JobFile
from app.models.processing_log import ProcessingLog

def build_file_inventory(job_id: int, upload_round_id: int, extracted_dir: str, db: Session) -> int:
    """
    Scans the extracted files folder, indexes each file into database, and logs a summary log.
    """
    print(f"Building file inventory for job ID: {job_id}, round ID: {upload_round_id} in {extracted_dir}")
    files_indexed = []

    for root, dirs, files in os.walk(extracted_dir):
        for filename in files:
            # Ignore hidden files, system files (like .DS_Store), and macOS archive metadata files
            if filename.startswith(".") or "__MACOSX" in root:
                continue

            full_path = os.path.join(root, filename)
            file_extension = os.path.splitext(filename)[1].lower().lstrip(".")
            
            # Store the relative path from the app root directory (e.g. storage/jobs/...)
            relative_path = os.path.relpath(full_path, os.getcwd())

            new_file = JobFile(
                tax_job_id=job_id,
                upload_round_id=upload_round_id,
                file_name=filename,
                file_path=relative_path,
                file_type=file_extension,
                is_processed=False
            )
            db.add(new_file)
            files_indexed.append(filename)

    db.commit()

    # Log summary details in processing_logs
    log_message = f"File inventory complete. Indexed {len(files_indexed)} files."
    if files_indexed:
        log_message += f" Files found: {', '.join(files_indexed[:8])}"
        if len(files_indexed) > 8:
            log_message += " ..."

    summary_log = ProcessingLog(
        tax_job_id=job_id,
        level=ProcessingLog.LEVEL_INFO,
        message=log_message
    )
    db.add(summary_log)
    db.commit()

    print(f"File inventory indexing complete. Count: {len(files_indexed)}")
    return len(files_indexed)
