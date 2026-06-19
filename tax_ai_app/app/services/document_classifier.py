import os
from sqlalchemy.orm import Session
from app.models.job_file import JobFile
from app.models.processing_log import ProcessingLog

# Document Types Constants (Section 12)
DOC_PRIOR_YEAR_RETURN = "PRIOR_YEAR_RETURN"
DOC_BALANCE_SHEET = "BALANCE_SHEET"
DOC_INCOME_STATEMENT = "INCOME_STATEMENT"
DOC_TRIAL_BALANCE = "TRIAL_BALANCE"
DOC_GENERAL_LEDGER = "GENERAL_LEDGER"
DOC_BANK_STATEMENT = "BANK_STATEMENT"
DOC_PAYROLL_SUMMARY = "PAYROLL_SUMMARY"
DOC_W2_W3 = "W2_W3"
DOC_FORM_1099 = "FORM_1099"
DOC_LOAN_STATEMENT = "LOAN_STATEMENT"
DOC_DEPRECIATION_SCHEDULE = "DEPRECIATION_SCHEDULE"
DOC_AR_AGING = "AR_AGING"
DOC_AP_AGING = "AP_AGING"
DOC_SHAREHOLDER_DISTRIBUTION = "SHAREHOLDER_DISTRIBUTION"
DOC_UNKNOWN = "UNKNOWN"

# Keyword maps for classification checks
KEYWORD_MAPS = {
    DOC_PRIOR_YEAR_RETURN: ["1120-s", "1065", "1120s", "form 1040", "schedule c", "prior year tax", "federal return"],
    DOC_TRIAL_BALANCE: ["trial balance", "trial bal", " tb "],
    DOC_BALANCE_SHEET: ["balance sheet", "assets", "liabilities", "retained earnings", "total equity"],
    DOC_INCOME_STATEMENT: ["income statement", "profit & loss", "profit and loss", "p&l", "p & l", "net income", "operating revenue"],
    DOC_GENERAL_LEDGER: ["general ledger", " gl ", "transaction detail", "ledger by account"],
    DOC_BANK_STATEMENT: ["bank statement", "statement period", "deposits", "withdrawals", "beginning balance", "ending balance"],
    DOC_PAYROLL_SUMMARY: ["payroll summary", "payroll journal", "payroll register", "wages", "payroll taxes"],
    DOC_W2_W3: ["w-2", "w-3", "wage and tax statement"],
    DOC_FORM_1099: ["1099-misc", "1099-nec", "1099-k", "form 1099"],
    DOC_LOAN_STATEMENT: ["loan statement", "loan balance", "interest paid", "amortization schedule"],
    DOC_DEPRECIATION_SCHEDULE: ["depreciation schedule", "fixed asset schedule", "accumulated depreciation", "depreciation expense"],
    DOC_AR_AGING: ["ar aging", "accounts receivable aging", "a/r aging", "customer aging", "receivable aging"],
    DOC_AP_AGING: ["ap aging", "accounts payable aging", "a/p aging", "vendor aging", "payable aging"],
    DOC_SHAREHOLDER_DISTRIBUTION: ["shareholder distribution", "partner distribution", "shareholder draw", "owner draw", "partner draw", "capital distribution"]
}

def classify_document(filename: str, text_content: str) -> str:
    """
    Classifies a document based on filename patterns and extracted text content.
    """
    fn_lower = filename.lower()
    txt_lower = text_content.lower()
    
    # 1. Match based on filename keywords first (faster, highly indicative)
    for doc_type, keywords in KEYWORD_MAPS.items():
        for kw in keywords:
            if kw in fn_lower:
                return doc_type
                
    # 2. Match based on extracted body text content
    for doc_type, keywords in KEYWORD_MAPS.items():
        match_count = 0
        for kw in keywords:
            if kw in txt_lower:
                match_count += 1
        # If multiple keywords matching the document type are found, classify it
        if match_count >= 2:
            return doc_type
            
    # Default fallback
    return DOC_UNKNOWN

def run_classification_phase(job_id: int, db: Session, round_ids: list[int] | None = None):
    """
    Iterates over files for a job, classifies them, and updates their database records.
    If round_ids is specified, only classifies files within those rounds.
    """
    print(f"[Classifier] Starting document classification for job ID: {job_id}")
    
    if round_ids:
        files = db.query(JobFile).filter(JobFile.tax_job_id == job_id, JobFile.upload_round_id.in_(round_ids)).all()
    else:
        files = db.query(JobFile).filter(JobFile.tax_job_id == job_id).all()
        
    classified_counts = {}
    
    for file_record in files:
        # Load extracted text content if it exists
        text_content = ""
        txt_file_path = os.path.join(os.getcwd(), file_record.file_path + ".txt")
        
        if os.path.exists(txt_file_path):
            try:
                with open(txt_file_path, "r", encoding="utf-8") as f:
                    text_content = f.read()
            except Exception as e:
                print(f"[Classifier] Warning: Could not read text file for {file_record.file_name}: {e}")
                
        # Run classification
        doc_type = classify_document(file_record.file_name, text_content)
        file_record.detected_document_type = doc_type
        
        # Track counts
        classified_counts[doc_type] = classified_counts.get(doc_type, 0) + 1
        print(f"[Classifier] Classified '{file_record.file_name}' as {doc_type}")
        
    db.commit()
    
    # Log classification summary details to processing_logs
    summary_msg = "Classification complete. Results: " + ", ".join([f"{k}: {v}" for k, v in classified_counts.items()])
    summary_log = ProcessingLog(
        tax_job_id=job_id,
        level=ProcessingLog.LEVEL_INFO,
        message=summary_msg
    )
    db.add(summary_log)
    db.commit()
    print(f"[Classifier] Completed classification for job ID {job_id}: {summary_msg}")
