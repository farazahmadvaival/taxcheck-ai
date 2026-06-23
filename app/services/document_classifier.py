import os
from sqlalchemy.orm import Session
from app.models.job_file import JobFile
from app.models.processing_log import ProcessingLog

# Document Types Constants
DOC_PRIOR_YEAR_RETURN = "PRIOR_YEAR_RETURN"
DOC_CURRENT_YEAR_RETURN = "CURRENT_YEAR_RETURN"
DOC_BALANCE_SHEET = "BALANCE_SHEET"
DOC_INCOME_STATEMENT = "INCOME_STATEMENT"
DOC_TRIAL_BALANCE = "TRIAL_BALANCE"
DOC_GENERAL_LEDGER = "GENERAL_LEDGER"
DOC_BANK_STATEMENT = "BANK_STATEMENT"
DOC_BANK_RECONCILIATION = "BANK_RECONCILIATION"
DOC_PAYROLL_SUMMARY = "PAYROLL_SUMMARY"
DOC_W2_W3 = "W2_W3"
DOC_FORM_941_940 = "FORM_941_940"
DOC_DEPRECIATION_SCHEDULE = "DEPRECIATION_SCHEDULE"
DOC_FIXED_ASSET_LISTING = "FIXED_ASSET_LISTING"
DOC_LOAN_STATEMENT = "LOAN_STATEMENT"
DOC_CREDIT_CARD_STATEMENT = "CREDIT_CARD_STATEMENT"
DOC_AR_AGING = "AR_AGING"
DOC_AP_AGING = "AP_AGING"
DOC_SHAREHOLDER_DISTRIBUTION = "SHAREHOLDER_DISTRIBUTION"
DOC_PARTNER_DISTRIBUTION = "PARTNER_DISTRIBUTION"
DOC_OWNER_DRAW_SUPPORT = "OWNER_DRAW_SUPPORT"
DOC_K1_WORKSHEET = "K1_WORKSHEET"
DOC_OWNERSHIP_SCHEDULE = "OWNERSHIP_SCHEDULE"
DOC_CAPITAL_ACCOUNT_SCHEDULE = "CAPITAL_ACCOUNT_SCHEDULE"
DOC_SALES_REPORT = "SALES_REPORT"
DOC_MERCHANT_STATEMENT = "MERCHANT_STATEMENT"
DOC_FORM_1099_K = "FORM_1099_K"
DOC_FORM_1099_NEC = "FORM_1099_NEC"
DOC_FORM_1099_MISC = "FORM_1099_MISC"
DOC_INVENTORY_REPORT = "INVENTORY_REPORT"
DOC_COGS_SUPPORT = "COGS_SUPPORT"
DOC_VEHICLE_MILEAGE_LOG = "VEHICLE_MILEAGE_LOG"
DOC_HOME_OFFICE_SUPPORT = "HOME_OFFICE_SUPPORT"
DOC_FORM_8829 = "FORM_8829"
DOC_CONTRACTOR_LISTING = "CONTRACTOR_LISTING"
DOC_W9 = "W9"
DOC_TAX_PAYMENT_SUPPORT = "TAX_PAYMENT_SUPPORT"
DOC_SALES_TAX_REPORT = "SALES_TAX_REPORT"
DOC_UNKNOWN = "UNKNOWN"

# Keyword maps for classification checks
KEYWORD_MAPS = {
    DOC_PRIOR_YEAR_RETURN: ["1120-s", "1065", "1120s", "form 1040", "schedule c", "prior year tax", "federal return", "prior year"],
    DOC_CURRENT_YEAR_RETURN: ["tax return 2025", "form 1120s 2025", "form 1065 2025"],
    DOC_TRIAL_BALANCE: ["trial balance", "trial bal", " tb "],
    DOC_BALANCE_SHEET: ["balance sheet", "assets", "liabilities", "retained earnings", "total equity"],
    DOC_INCOME_STATEMENT: ["income statement", "profit & loss", "profit and loss", "p&l", "p & l", "net income", "operating revenue"],
    DOC_GENERAL_LEDGER: ["general ledger", " gl ", "transaction detail", "ledger by account"],
    DOC_BANK_STATEMENT: ["bank statement", "statement period", "deposits", "withdrawals", "beginning balance", "ending balance"],
    DOC_BANK_RECONCILIATION: ["bank reconciliation", "bank recon", "outstanding checks", "deposits in transit"],
    DOC_PAYROLL_SUMMARY: ["payroll summary", "payroll journal", "payroll register", "payroll taxes"],
    DOC_W2_W3: ["w-2", "w-3", "wage and tax statement"],
    DOC_FORM_941_940: ["941", "940", "employer's quarterly federal", "employer's annual unemployment"],
    DOC_DEPRECIATION_SCHEDULE: ["depreciation schedule", "fixed asset schedule", "accumulated depreciation", "depreciation expense"],
    DOC_FIXED_ASSET_LISTING: ["fixed asset listing", "fixed assets", "asset additions", "capital improvements"],
    DOC_LOAN_STATEMENT: ["loan statement", "loan balance", "interest paid", "amortization schedule"],
    DOC_CREDIT_CARD_STATEMENT: ["credit card statement", "card statement", "visa statement", "mastercard statement", "amex statement"],
    DOC_AR_AGING: ["ar aging", "accounts receivable aging", "a/r aging", "customer aging", "receivable aging"],
    DOC_AP_AGING: ["ap aging", "accounts payable aging", "a/p aging", "vendor aging", "payable aging"],
    DOC_SHAREHOLDER_DISTRIBUTION: ["shareholder distribution", "shareholder draw", "capital distribution"],
    DOC_PARTNER_DISTRIBUTION: ["partner distribution", "partner draw", "partnership distribution"],
    DOC_OWNER_DRAW_SUPPORT: ["owner draw", "proprietor draw", "drawings", "owner personal transactions"],
    DOC_K1_WORKSHEET: ["schedule k-1", "k-1 worksheet", "partner's share of income"],
    DOC_OWNERSHIP_SCHEDULE: ["ownership schedule", "shareholder percentage", "partner percentage"],
    DOC_CAPITAL_ACCOUNT_SCHEDULE: ["capital account", "partner's capital", "schedule m-2"],
    DOC_SALES_REPORT: ["sales report", "sales register", "gross revenue summary"],
    DOC_MERCHANT_STATEMENT: ["merchant statement", "stripe statement", "square statement", "merchant fees"],
    DOC_FORM_1099_K: ["1099-k", "1099k", "merchant card and third party"],
    DOC_FORM_1099_NEC: ["1099-nec", "1099nec", "nonemployee compensation"],
    DOC_FORM_1099_MISC: ["1099-misc", "1099misc", "miscellaneous income"],
    DOC_INVENTORY_REPORT: ["inventory report", "physical inventory", "stock count", "inventory listing"],
    DOC_COGS_SUPPORT: ["cost of goods sold", "cogs schedule", "cogs support"],
    DOC_VEHICLE_MILEAGE_LOG: ["mileage log", "vehicle log", "auto mileage", "business miles"],
    DOC_HOME_OFFICE_SUPPORT: ["home office", "business use of home", "utilities worksheet"],
    DOC_FORM_8829: ["8829", "form 8829", "expenses for business use of home"],
    DOC_CONTRACTOR_LISTING: ["contractor list", "subcontractor list", "1099 listing"],
    DOC_W9: ["w-9", "w9", "taxpayer identification number and certification"],
    DOC_TAX_PAYMENT_SUPPORT: ["tax payment receipt", "eftps receipt", "estimated tax payment"],
    DOC_SALES_TAX_REPORT: ["sales tax return", "sales tax report", "state sales tax filings"]
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
