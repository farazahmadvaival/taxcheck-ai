import os
import re
from sqlalchemy.orm import Session
from app.models.job_file import JobFile
from app.models.checklist_item import ChecklistItem
from app.models.processing_log import ProcessingLog

def extract_numeric_value(line: str) -> float | None:
    """Helper to extract a float number from a text line, handling commas and parenthesis (negatives)."""
    # Remove currency signs
    clean_line = line.replace("$", "")
    # Find all tokens that look like numbers (with optional parenthesis or minus sign)
    tokens = clean_line.split()
    numbers = []
    for token in tokens:
        # Strip trailing punctuation like commas, but not dots or parens
        t = token.rstrip(",:")
        # Check if it represents a number
        match = re.search(r'^\(?-?[0-9,]+\.?[0-9]*\)?$', t)
        if match:
            # Clean it to see if we can convert it to float
            val_str = t.replace(",", "").replace("(", "").replace(")", "")
            try:
                val = float(val_str)
                if "(" in t or "-" in t:
                    val = -abs(val)
                numbers.append(val)
            except ValueError:
                pass
                
    if numbers:
        # Usually, the first number in the columns is the current year value
        return numbers[0]
    return None

def analyze_balance_sheet(text: str) -> tuple[float | None, float | None, float | None]:
    """Scans text to extract Total Assets, Total Liabilities, and Total Equity."""
    assets = None
    liabilities = None
    equity = None
    
    for line in text.split("\n"):
        line_lower = line.lower()
        # Look for total assets label
        if "total" in line_lower and "asset" in line_lower:
            # Make sure it's not "current assets" or "fixed assets" or "other assets"
            if not any(x in line_lower for x in ["current", "fixed", "other", "net"]):
                val = extract_numeric_value(line)
                if val is not None:
                    assets = val
        # Look for total liabilities label
        elif "total" in line_lower and "liabilit" in line_lower:
            if not any(x in line_lower for x in ["current", "other", "equity", "capital"]):
                val = extract_numeric_value(line)
                if val is not None:
                    liabilities = val
        # Look for total equity label
        elif "total" in line_lower and ("equity" in line_lower or "capital" in line_lower):
            if not any(x in line_lower for x in ["liabilit"]):
                val = extract_numeric_value(line)
                if val is not None:
                    equity = val
                    
    return assets, liabilities, equity

def run_anomaly_rules(job_id: int, db: Session):
    """
    Executes Section 13 missing-document and financial anomaly checking rules.
    """
    print(f"[AnomalyEngine] Running rules for job ID: {job_id}")
    
    # 1. Gather classified files and aggregate document types
    files = db.query(JobFile).filter(JobFile.tax_job_id == job_id).all()
    doc_types = {f.detected_document_type for f in files if f.detected_document_type}
    
    # Combine all file texts for keyword checking
    all_text_content = ""
    for file_record in files:
        txt_path = os.path.join(os.getcwd(), file_record.file_path + ".txt")
        if os.path.exists(txt_path):
            try:
                with open(txt_path, "r", encoding="utf-8") as f:
                    all_text_content += "\n" + f.read()
            except Exception:
                pass
                
    all_text_lower = all_text_content.lower()
    
    # Clear existing checklist items for this job to support reprocessing safely
    db.query(ChecklistItem).filter(ChecklistItem.tax_job_id == job_id).delete()
    db.commit()
    
    findings = []
    
    # --- RULE A: Missing prior return ---
    if "PRIOR_YEAR_RETURN" not in doc_types:
        findings.append(ChecklistItem(
            tax_job_id=job_id,
            type=ChecklistItem.TYPE_MISSING_DOCUMENT,
            title="Prior Year Tax Return Missing",
            description="No prior year tax return (Form 1120-S, 1065, or 1040) was detected in the upload inventory.",
            severity=ChecklistItem.SEVERITY_HIGH,
            status=ChecklistItem.STATUS_OPEN,
            recommended_document="Prior year federal tax return",
            email_text="Please provide the prior year federal tax return so we can verify entity details and carryforward balances."
        ))

    # --- RULE B: Missing balance sheet ---
    if "BALANCE_SHEET" not in doc_types:
        findings.append(ChecklistItem(
            tax_job_id=job_id,
            type=ChecklistItem.TYPE_MISSING_DOCUMENT,
            title="Balance Sheet Missing",
            description="No current year balance sheet was detected in the document inventory.",
            severity=ChecklistItem.SEVERITY_HIGH,
            status=ChecklistItem.STATUS_OPEN,
            recommended_document="Current year balance sheet",
            email_text="Please provide the current year balance sheet so we can reconcile asset, liability, and equity accounts."
        ))

    # --- RULE C: Missing income statement ---
    if "INCOME_STATEMENT" not in doc_types:
        findings.append(ChecklistItem(
            tax_job_id=job_id,
            type=ChecklistItem.TYPE_MISSING_DOCUMENT,
            title="Income Statement Missing",
            description="No current year income statement or profit & loss (P&L) was detected.",
            severity=ChecklistItem.SEVERITY_HIGH,
            status=ChecklistItem.STATUS_OPEN,
            recommended_document="Current year income statement / P&L",
            email_text="Please provide the current year profit & loss statement so we can audit revenue and business expenses."
        ))

    # --- RULE D: Missing trial balance ---
    if "TRIAL_BALANCE" not in doc_types and "BALANCE_SHEET" in doc_types and "INCOME_STATEMENT" in doc_types:
        findings.append(ChecklistItem(
            tax_job_id=job_id,
            type=ChecklistItem.TYPE_MISSING_DOCUMENT,
            title="Trial Balance Missing",
            description="Balance sheet and income statement were found, but no account-level trial balance was detected.",
            severity=ChecklistItem.SEVERITY_HIGH,
            status=ChecklistItem.STATUS_OPEN,
            recommended_document="Current year trial balance",
            email_text="Please provide the current year trial balance so we can verify account-level balances and classifications."
        ))

    # --- RULE E: Missing general ledger ---
    if "GENERAL_LEDGER" not in doc_types and ("TRIAL_BALANCE" in doc_types or "BALANCE_SHEET" in doc_types):
        findings.append(ChecklistItem(
            tax_job_id=job_id,
            type=ChecklistItem.TYPE_MISSING_DOCUMENT,
            title="General Ledger Detail Missing",
            description="Financial reports are present, but the general ledger containing transactional entries is missing.",
            severity=ChecklistItem.SEVERITY_MEDIUM,
            status=ChecklistItem.STATUS_OPEN,
            recommended_document="General ledger detail report",
            email_text="Please provide the transaction-level general ledger detail report to support auditing classifications."
        ))

    # --- RULE F: Payroll support missing ---
    if "PAYROLL_SUMMARY" not in doc_types and "W2_W3" not in doc_types:
        if any(w in all_text_lower for w in ["wages", "payroll", "salaries", "officer compensation"]):
            findings.append(ChecklistItem(
                tax_job_id=job_id,
                type=ChecklistItem.TYPE_MISSING_DOCUMENT,
                title="Payroll Support Missing",
                description="Payroll or salary expense entries were detected, but no supporting payroll summary, W-2, or W-3 reports were uploaded.",
                severity=ChecklistItem.SEVERITY_HIGH,
                status=ChecklistItem.STATUS_OPEN,
                recommended_document="Payroll summary, Form W-2/W-3, or quarterly payroll tax filings",
                email_text="Please provide the annual payroll summary, W-2/W-3 reports, or quarterly tax filings to substantiate employee compensation expenses."
            ))

    # --- RULE G: Depreciation support missing ---
    if "DEPRECIATION_SCHEDULE" not in doc_types:
        if any(w in all_text_lower for w in ["depreciation", "fixed assets", "accumulated depreciation", "depreciation expense"]):
            findings.append(ChecklistItem(
                tax_job_id=job_id,
                type=ChecklistItem.TYPE_MISSING_DOCUMENT,
                title="Depreciation Schedule Missing",
                description="Depreciation expenses or fixed asset items were found, but the supporting asset depreciation schedule is missing.",
                severity=ChecklistItem.SEVERITY_MEDIUM,
                status=ChecklistItem.STATUS_OPEN,
                recommended_document="Fixed asset depreciation schedule",
                email_text="Please provide the detailed fixed asset and depreciation schedule so we can reconcile tax depreciation adjustments."
            ))

    # --- RULE H: Loan support missing ---
    if "LOAN_STATEMENT" not in doc_types:
        if any(w in all_text_lower for w in ["loan", "interest expense", "notes payable", "mortgage", "lender"]):
            findings.append(ChecklistItem(
                tax_job_id=job_id,
                type=ChecklistItem.TYPE_MISSING_DOCUMENT,
                title="Loan / Interest Statement Missing",
                description="Loan liabilities or interest expenses were detected, but no lender statements were provided.",
                severity=ChecklistItem.SEVERITY_MEDIUM,
                status=ChecklistItem.STATUS_OPEN,
                recommended_document="Lender loan statements showing principal and interest breakdowns",
                email_text="Please provide year-end statements or loan agreements showing interest breakdowns and outstanding balances."
            ))

    # --- RULE I: Bank support missing ---
    if "BANK_STATEMENT" not in doc_types:
        if any(w in all_text_lower for w in ["cash", "bank account", "checking account", "savings account"]):
            findings.append(ChecklistItem(
                tax_job_id=job_id,
                type=ChecklistItem.TYPE_MISSING_DOCUMENT,
                title="Bank Statement Missing",
                description="Cash accounts or banking transactions were detected, but no December bank statements or reconciliation worksheets exist.",
                severity=ChecklistItem.SEVERITY_HIGH,
                status=ChecklistItem.STATUS_OPEN,
                recommended_document="December bank statements and reconciliation reports",
                email_text="Please provide December bank statements and reconciliation reports for all active cash accounts."
            ))

    # --- RULE J: AR support missing ---
    if "AR_AGING" not in doc_types:
        if any(w in all_text_lower for w in ["accounts receivable", "trade receivables", "customer receivables", "receivables", "a/r"]):
            findings.append(ChecklistItem(
                tax_job_id=job_id,
                type=ChecklistItem.TYPE_MISSING_DOCUMENT,
                title="Accounts Receivable Aging Missing",
                description="Accounts receivable balances were detected, but no supporting accounts receivable (AR) aging report was uploaded.",
                severity=ChecklistItem.SEVERITY_MEDIUM,
                status=ChecklistItem.STATUS_OPEN,
                recommended_document="Accounts receivable (AR) aging report",
                email_text="Please provide the accounts receivable (AR) aging report as of year-end to support the trade receivables balance."
            ))

    # --- RULE K: AP support missing ---
    if "AP_AGING" not in doc_types:
        if any(w in all_text_lower for w in ["accounts payable", "payables", "trade payables", "trade creditors", "a/p"]):
            findings.append(ChecklistItem(
                tax_job_id=job_id,
                type=ChecklistItem.TYPE_MISSING_DOCUMENT,
                title="Accounts Payable Aging Missing",
                description="Accounts payable balances were detected, but no supporting accounts payable (AP) aging report was uploaded.",
                severity=ChecklistItem.SEVERITY_MEDIUM,
                status=ChecklistItem.STATUS_OPEN,
                recommended_document="Accounts payable (AP) aging report",
                email_text="Please provide the accounts payable (AP) aging report as of year-end to support the trade payables balance."
            ))

    # --- RULE L: High miscellaneous expense ---
    misc_exceeds = False
    detected_misc_val = 0.0
    for line in all_text_content.split("\n"):
        line_lower = line.lower()
        if ("miscellaneous" in line_lower or "misc" in line_lower) and ("expense" in line_lower or "expenses" in line_lower or "deduction" in line_lower):
            val = extract_numeric_value(line)
            if val is not None and abs(val) > 10000.0:
                misc_exceeds = True
                detected_misc_val = abs(val)
                break
    # Fallback to general keyword scan if no exact value extracted
    if not misc_exceeds and any(w in all_text_lower for w in ["miscellaneous expense", "misc expense", "miscellaneous expenses", "misc expenses"]):
         misc_exceeds = True
         
    if misc_exceeds:
        desc = "Miscellaneous expenses exceeding our configured audit threshold of $10,000.00 were detected."
        if detected_misc_val > 0.0:
            desc = f"Miscellaneous expenses of ${detected_misc_val:,.2f} were detected, which exceeds our configured audit threshold of $10,000.00."
        findings.append(ChecklistItem(
            tax_job_id=job_id,
            type=ChecklistItem.TYPE_ANOMALY,
            title="High Miscellaneous Expense",
            description=desc,
            severity=ChecklistItem.SEVERITY_MEDIUM,
            status=ChecklistItem.STATUS_OPEN,
            recommended_document="General ledger breakdown of miscellaneous expenses",
            email_text="Please provide a detailed general ledger breakdown or transaction list for miscellaneous expenses, as they exceed our review threshold."
        ))

    # --- RULE M: Shareholder distribution support missing ---
    if "SHAREHOLDER_DISTRIBUTION" not in doc_types:
        if any(w in all_text_lower for w in [
            "shareholder distribution", "shareholder distributions", "partner distribution", 
            "partner distributions", "owner draw", "owner draws", "officer draw", "officer draws", 
            "shareholder draw", "shareholder draws", "due from shareholder", "due from officer", 
            "loan to shareholder", "loan to officer", "capital distribution"
        ]):
            findings.append(ChecklistItem(
                tax_job_id=job_id,
                type=ChecklistItem.TYPE_MISSING_DOCUMENT,
                title="Shareholder Distribution Support Missing",
                description="Shareholder distributions, draws, or officer cash advances were detected, but no supporting distribution schedule or ledger details were provided.",
                severity=ChecklistItem.SEVERITY_MEDIUM,
                status=ChecklistItem.STATUS_OPEN,
                recommended_document="Shareholder distribution schedule or owner draw ledger details",
                email_text="Please provide documentation or ledger details for shareholder distributions, draws, or owner transactions to verify tax treatment."
            ))

    # --- RULE N: Negative balance warning ---
    negative_accounts = []
    for line in all_text_content.split("\n"):
        line_lower = line.lower()
        if any(kw in line_lower for kw in ["cash", "accounts receivable", "accounts payable", "inventory", "notes payable", "credit card"]):
            # Look for negative numbers represented by a minus sign or in parentheses
            if re.search(r'-\s*\$?[0-9,]+\.?[0-9]*', line) or re.search(r'\(\s*\$?[0-9,]+\.?[0-9]*\)', line):
                val = extract_numeric_value(line)
                if val is not None and val < 0:
                    account_match = re.match(r'^\s*([A-Za-z0-9\s/&_-]+)', line)
                    acc_name = account_match.group(1).strip() if account_match else "Asset/Liability"
                    negative_accounts.append(f"{acc_name} ({val:,.2f})")
                    
    if negative_accounts:
        accounts_list = ", ".join(negative_accounts[:3])
        if len(negative_accounts) > 3:
            accounts_list += " etc."
        findings.append(ChecklistItem(
            tax_job_id=job_id,
            type=ChecklistItem.TYPE_WARNING,
            title="Negative Account Balance Warning",
            description=f"Negative asset or liability balances were detected in the financial records (e.g., {accounts_list}), which may indicate classification or reconciliation errors.",
            severity=ChecklistItem.SEVERITY_LOW,
            status=ChecklistItem.STATUS_OPEN,
            recommended_document="Explanation or reclassification entries for negative balance accounts",
            email_text="Please provide reconciliation details or reclassification explanations for the negative account balances identified."
        ))

    # --- MATHEMATICAL CROSS-CHECKS: Balance sheet mismatch ---
    bs_files = db.query(JobFile).filter(
        JobFile.tax_job_id == job_id,
        JobFile.detected_document_type == "BALANCE_SHEET"
    ).all()
    
    for bs_file in bs_files:
        txt_path = os.path.join(os.getcwd(), bs_file.file_path + ".txt")
        if os.path.exists(txt_path):
            try:
                with open(txt_path, "r", encoding="utf-8") as f:
                    text_content = f.read()
                
                assets, liabilities, equity = analyze_balance_sheet(text_content)
                print(f"[AnomalyEngine] BS '{bs_file.file_name}' values: Assets={assets}, Liab={liabilities}, Equity={equity}")
                
                if assets is not None and liabilities is not None and equity is not None:
                    difference = abs(assets - (liabilities + equity))
                    # Allow a $5 rounding difference threshold
                    if difference > 5.0:
                        findings.append(ChecklistItem(
                            tax_job_id=job_id,
                            type=ChecklistItem.TYPE_ANOMALY,
                            title="Balance Sheet Equation Mismatch",
                            description=f"Mathematical discrepancy in balance sheet '{bs_file.file_name}': Assets (${assets:,.2f}) != Liabilities (${liabilities:,.2f}) + Equity (${equity:,.2f}). Mismatch is ${difference:,.2f}.",
                            severity=ChecklistItem.SEVERITY_HIGH,
                            status=ChecklistItem.STATUS_OPEN,
                            recommended_document="Corrected balance sheet or trial balance ledger",
                            email_text=f"Please reconcile the balance sheet since the balance sheet equation does not balance: Assets (${assets:,.2f}) != Liabilities (${liabilities:,.2f}) + Equity (${equity:,.2f})."
                        ))
            except Exception as math_err:
                print(f"[AnomalyEngine] Error during BS math check for {bs_file.file_name}: {math_err}")

    # 4. Save all raised findings into the checklist_items table
    for item in findings:
        db.add(item)
    db.commit()
    
    # 5. Log summary of execution
    summary_msg = f"Rule execution matrix complete. Raised {len(findings)} checklist items."
    summary_log = ProcessingLog(
        tax_job_id=job_id,
        level=ProcessingLog.LEVEL_INFO,
        message=summary_msg
    )
    db.add(summary_log)
    db.commit()
    
    print(f"[AnomalyEngine] Completed rule checks. Raised: {len(findings)}")
    return len(findings)
