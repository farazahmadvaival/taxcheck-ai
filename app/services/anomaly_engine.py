import os
import re
import json
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.job_file import JobFile
from app.models.checklist_item import ChecklistItem
from app.models.processing_log import ProcessingLog
from app.models.tax_job import TaxJob
from app.models.extracted_financial_value import ExtractedFinancialValue
from app.services.llm_service import client as gemini_client
from app.config import ANOMALY_RULE_CONFIG


# Constants for return type checks
RETURN_TYPE_KEYWORDS = {
    "1120-S": ["1120-S", "1120s", "S corporation", "shareholder", "Schedule K-1"],
    "1065": ["1065", "partnership", "partner", "Schedule K-1", "Form 1065"],
    "1120": ["1120", "C corporation", "corporation", "dividends"],
    "1040_SCHEDULE_C": ["Schedule C", "sole proprietor", "business income", "Form 1040"]
}

def extract_numeric_value(line: str) -> float | None:
    """Helper to extract a float number from a text line, handling commas and parenthesis (negatives)."""
    clean_line = line.replace("$", "")
    tokens = clean_line.split()
    numbers = []
    for token in tokens:
        t = token.rstrip(",:")
        match = re.search(r'^\(?-?[0-9,]+\.?[0-9]*\)?$', t)
        if match:
            val_str = t.replace(",", "").replace("(", "").replace(")", "")
            try:
                val = float(val_str)
                if "(" in t or "-" in t:
                    val = -abs(val)
                numbers.append(val)
            except ValueError:
                pass
                
    if numbers:
        return numbers[0]
    return None

def extract_numeric_values_from_line(line: str) -> list[float]:
    """Helper to extract all numbers from a text line to support beginning and ending balance sheet values."""
    clean_line = line.replace("$", "")
    tokens = clean_line.split()
    numbers = []
    for token in tokens:
        t = token.rstrip(",:")
        match = re.search(r'^\(?-?[0-9,]+\.?[0-9]*\)?$', t)
        if match:
            val_str = t.replace(",", "").replace("(", "").replace(")", "")
            try:
                val = float(val_str)
                if "(" in t or "-" in t:
                    val = -abs(val)
                numbers.append(val)
            except ValueError:
                pass
    return numbers

def analyze_balance_sheet(text: str) -> tuple[float | None, float | None, float | None]:
    """Scans text to extract Total Assets, Total Liabilities, and Total Equity."""
    assets = None
    liabilities = None
    equity = None
    
    for line in text.split("\n"):
        line_lower = line.lower()
        if "total" in line_lower and "asset" in line_lower:
            if not any(x in line_lower for x in ["current", "fixed", "other", "net"]):
                val = extract_numeric_value(line)
                if val is not None:
                    assets = val
        elif "total" in line_lower and "liabilit" in line_lower:
            if not any(x in line_lower for x in ["current", "other", "equity", "capital"]):
                val = extract_numeric_value(line)
                if val is not None:
                    liabilities = val
        elif "total" in line_lower and ("equity" in line_lower or "capital" in line_lower):
            if not any(x in line_lower for x in ["liabilit"]):
                val = extract_numeric_value(line)
                if val is not None:
                    equity = val
                    
    return assets, liabilities, equity

def harvest_financial_metrics_regex(text: str) -> dict[str, float]:
    """Scans text line-by-line using heuristics to extract key financial values."""
    extracted = {}
    lines = text.split("\n")
    for line in lines:
        line_lower = line.lower()
        nums = extract_numeric_values_from_line(line)
        if not nums:
            continue
            
        # Total Assets
        if "total" in line_lower and "asset" in line_lower and not any(x in line_lower for x in ["current", "fixed", "other", "net"]):
            if len(nums) >= 2:
                extracted["total_assets_ending"] = nums[0]
                extracted["total_assets_beginning"] = nums[1]
            else:
                extracted["total_assets_ending"] = nums[0]
                
        # Total Liabilities
        elif "total" in line_lower and "liabilit" in line_lower and not any(x in line_lower for x in ["current", "other", "equity", "capital"]):
            if len(nums) >= 2:
                extracted["total_liabilities_ending"] = nums[0]
                extracted["total_liabilities_beginning"] = nums[1]
            else:
                extracted["total_liabilities_ending"] = nums[0]
                
        # Total Equity
        elif "total" in line_lower and ("equity" in line_lower or "capital" in line_lower) and not "liabilit" in line_lower:
            if len(nums) >= 2:
                extracted["total_equity_ending"] = nums[0]
                extracted["total_equity_beginning"] = nums[1]
            else:
                extracted["total_equity_ending"] = nums[0]
                
        # Gross Receipts
        elif ("gross" in line_lower and "receipt" in line_lower) or ("gross" in line_lower and "revenue" in line_lower) or ("total" in line_lower and "revenue" in line_lower):
            extracted["gross_receipts"] = nums[0]
            
        # COGS
        elif "cost of goods" in line_lower or "cogs" in line_lower:
            extracted["cost_of_goods_sold"] = nums[0]
            
        # Gross Profit
        elif "gross profit" in line_lower:
            extracted["gross_profit"] = nums[0]
            
        # Net Income
        elif "net income" in line_lower or "net profit" in line_lower:
            extracted["net_income"] = nums[0]
            
        # Cash Ending
        elif ("cash" in line_lower or "checking" in line_lower or "operating" in line_lower) and not any(x in line_lower for x in ["flow", "disbursements", "receipts"]):
            extracted["cash_ending"] = nums[0]
            
        # Accounts Receivable
        elif "accounts receivable" in line_lower or "a/r" in line_lower:
            extracted["accounts_receivable_ending"] = nums[0]
            
        # Accounts Payable
        elif "accounts payable" in line_lower or "a/p" in line_lower:
            extracted["accounts_payable_ending"] = nums[0]
            
        # Inventory
        elif "inventory" in line_lower or "merchandise" in line_lower:
            extracted["inventory_ending"] = nums[0]
            
        # Accumulated Depreciation
        elif "accumulated depreciation" in line_lower or "acc. depreciation" in line_lower:
            extracted["accumulated_depreciation"] = nums[0]
            
        # Notes Payable / Loans
        elif "notes payable" in line_lower or "loans payable" in line_lower:
            extracted["notes_payable"] = nums[0]
            
        # Shareholder/Partner Distributions
        elif "distribution" in line_lower or "owner draw" in line_lower or "proprietor draw" in line_lower:
            extracted["shareholder_distributions"] = nums[0]
            extracted["partner_distributions"] = nums[0]
            
        # Retained Earnings
        elif "retained earnings" in line_lower or "accumulated adjustments" in line_lower:
            if "beginning" in line_lower or "start" in line_lower:
                extracted["retained_earnings_beginning"] = nums[0]
            elif "ending" in line_lower or "end" in line_lower:
                extracted["retained_earnings_ending"] = nums[0]
            elif len(nums) >= 2:
                extracted["retained_earnings_ending"] = nums[0]
                extracted["retained_earnings_beginning"] = nums[1]
                
        # Beginning Capital
        elif "beginning" in line_lower and ("capital" in line_lower or "partner's capital" in line_lower or "shareholder's capital" in line_lower) and not "prior" in line_lower:
            extracted["beginning_capital"] = nums[0]
            
        # Current Year Income
        elif "current year" in line_lower and ("income" in line_lower or "net income" in line_lower):
            extracted["current_year_income"] = nums[0]
            
        # Capital Contributions
        elif "contribution" in line_lower and ("capital" in line_lower or "partner" in line_lower or "shareholder" in line_lower):
            extracted["capital_contributions"] = nums[0]
            
        # Prior Year Ending Capital
        elif "prior year" in line_lower and "ending" in line_lower and "capital" in line_lower:
            extracted["prior_year_ending_capital"] = nums[0]
            
        # Current Year Beginning Capital
        elif "current year" in line_lower and "beginning" in line_lower and "capital" in line_lower:
            extracted["current_year_beginning_capital"] = nums[0]
                
    return extracted

def harvest_financial_metrics_llm(text: str, filename: str, missing_keys: list[str]) -> dict[str, float]:
    """Fallback LLM query to extract specific key financial metrics from documents."""
    if not gemini_client or not gemini_client.api_key:
        return {}
        
    prompt = f"""
    You are a professional CPA tax preparation assistant.
    Analyze the following financial statement text from file '{filename}'.
    Extract the numeric values for the following missing keys:
    {", ".join(missing_keys)}
    
    Guidelines:
    1. Values must be plain numbers (floats), representing the final balance for the current tax year (ending) unless beginning balance is specified.
    2. Convert any negative numbers (in parentheses or with minus sign) to floats.
    3. Return a clean, valid JSON object ONLY containing the extracted keys and their values. Do not wrap in markdown or backticks.
    
    Example output format:
    {{
      "total_assets_ending": 125000.0,
      "net_income": 45000.0
    }}
    
    Document text:
    {text[:8000]}
    """
    try:
        res = gemini_client.generate_content(prompt)
        if res.startswith("```"):
            lines = res.split("\n")
            if lines[0].startswith("```"):
                res = "\n".join(lines[1:-1])
        data = json.loads(res.strip())
        return {k: float(v) for k, v in data.items() if k in missing_keys}
    except Exception as e:
        print(f"[AnomalyEngine] Gemini LLM extraction fallback failed: {e}")
        return {}

def harvest_job_financial_metrics(job_id: int, db: Session):
    """Harvests financial values from all processed job files, populating the database table."""
    files = db.query(JobFile).filter(JobFile.tax_job_id == job_id, JobFile.is_processed == True).all()
    
    # Clean previous extractions to allow reprocessing
    db.query(ExtractedFinancialValue).filter(ExtractedFinancialValue.tax_job_id == job_id).delete()
    db.commit()
    
    all_keys = [
        "total_assets_beginning", "total_assets_ending", "total_liabilities_beginning", "total_liabilities_ending",
        "total_equity_beginning", "total_equity_ending", "gross_receipts", "cost_of_goods_sold", "gross_profit",
        "net_income", "cash_ending", "accounts_receivable_ending", "accounts_payable_ending", "inventory_ending",
        "fixed_assets_cost", "accumulated_depreciation", "notes_payable", "shareholder_distributions",
        "partner_distributions", "retained_earnings_beginning", "retained_earnings_ending",
        "beginning_capital", "current_year_income", "capital_contributions",
        "shareholder_ownership_percentages", "shareholder_distribution_percentages",
        "prior_year_ending_capital", "current_year_beginning_capital"
    ]
    
    for job_file in files:
        txt_path = os.path.join(os.getcwd(), job_file.file_path + ".txt")
        if not os.path.exists(txt_path):
            continue
            
        try:
            with open(txt_path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception:
            continue
            
        # 1. Deterministic Extraction
        metrics = harvest_financial_metrics_regex(text)
        
        # 2. LLM Fallback for critical missing metrics based on doc type
        missing_keys = [k for k in all_keys if k not in metrics]
        if missing_keys and len(missing_keys) < len(all_keys):
            is_balance_sheet = job_file.detected_document_type == "BALANCE_SHEET"
            is_pnl = job_file.detected_document_type == "INCOME_STATEMENT"
            
            relevant_missing = []
            if is_balance_sheet:
                relevant_missing = [k for k in missing_keys if "asset" in k or "liabilit" in k or "equity" in k or "cash" in k or "receivable" in k or "payable" in k or "inventory" in k or "retained" in k or "capital" in k]
            elif is_pnl:
                relevant_missing = [k for k in missing_keys if "receipts" in k or "cogs" in k or "profit" in k or "income" in k]
                
            if relevant_missing:
                print(f"[AnomalyEngine] Running LLM fallback for {job_file.file_name} to extract: {relevant_missing}")
                llm_metrics = harvest_financial_metrics_llm(text, job_file.file_name, relevant_missing)
                metrics.update(llm_metrics)
                
        # 3. Save to database
        for k, v in metrics.items():
            if isinstance(v, (list, dict)):
                db.add(ExtractedFinancialValue(
                    tax_job_id=job_id,
                    job_file_id=job_file.id,
                    value_key=k,
                    amount=None,
                    confidence_score=job_file.confidence_score,
                    source_text=json.dumps(v)
                ))
            else:
                db.add(ExtractedFinancialValue(
                    tax_job_id=job_id,
                    job_file_id=job_file.id,
                    value_key=k,
                    amount=v,
                    confidence_score=job_file.confidence_score,
                    source_text=f"Extracted from {job_file.file_name}"
                ))
            
    db.commit()

def get_extracted_values(job_id: int, db: Session) -> dict:
    """Helper to query the database and compile a single dict of high-confidence extracted values."""
    values = db.query(ExtractedFinancialValue).filter(ExtractedFinancialValue.tax_job_id == job_id).all()
    res = {}
    for val in values:
        if val.value_key not in res or (val.confidence_score or 0) > (res[val.value_key].confidence_score or 0):
            res[val.value_key] = val
            
    res_dict = {}
    for k, v in res.items():
        if k in ["shareholder_ownership_percentages", "shareholder_distribution_percentages"]:
            try:
                res_dict[k] = json.loads(v.source_text)
            except Exception:
                res_dict[k] = float(v.amount) if v.amount is not None else None
        else:
            res_dict[k] = float(v.amount) if v.amount is not None else None
    return res_dict

def check_rule_preconditions(
    required_documents: list[str] | None = None,
    required_values: list[str] | None = None,
    uploaded_doc_types: list[str] | None = None,
    extracted_values: dict | None = None
) -> tuple[bool, str | None]:
    uploaded_doc_types = uploaded_doc_types or []
    extracted_values = extracted_values or {}
    
    if required_documents:
        missing_docs = [doc for doc in required_documents if doc not in uploaded_doc_types]
        if missing_docs:
            return False, f"Missing required document(s): {', '.join(missing_docs)}"
            
    if required_values:
        missing_vals = [val for val in required_values if val not in extracted_values or extracted_values[val] is None]
        if missing_vals:
            return False, f"Missing required extracted value(s): {', '.join(missing_vals)}"
            
    return True, None

def check_tie_out(
    extracted_amount: float,
    expected_amount: float,
    tolerance: float = None
) -> dict:
    if tolerance is None:
        tolerance = ANOMALY_RULE_CONFIG.get("default_tolerance_amount", 5.0)
    difference = abs(extracted_amount - expected_amount)

    return {
        "passed": difference <= tolerance,
        "difference": difference,
        "tolerance": tolerance
    }

def make_anomaly_result(
    rule_id: str,
    rule_name: str,
    category: str,
    severity: str = "MEDIUM",
    status: str = "PASSED",
    confidence_score: float = None,
    return_type: str | None = None,
    evidence_document: str | None = None,
    evidence_text: str | None = None,
    extracted_amount: float | None = None,
    expected_amount: float | None = None,
    difference: float | None = None,
    tolerance: float | None = None,
    missing_support: list[str] | None = None,
    recommended_action: str = "",
    review_required_by: str = "TAX_PREPARER",
    skip_reason: str | None = None
) -> dict:
    if confidence_score is None:
        confidence_score = ANOMALY_RULE_CONFIG.get("default_confidence_score", 0.75)
    return {
        "rule_id": rule_id,
        "rule_name": rule_name,
        "category": category,
        "severity": severity,
        "status": status,
        "confidence_score": confidence_score,
        "return_type": return_type,
        "evidence_document": evidence_document,
        "evidence_text": evidence_text,
        "extracted_amount": extracted_amount,
        "expected_amount": expected_amount,
        "difference": difference,
        "tolerance": tolerance,
        "missing_support": missing_support or [],
        "recommended_action": recommended_action,
        "review_required_by": review_required_by,
        "skip_reason": skip_reason
    }

def map_anomaly_result_to_checklist_item(job_id: int, res: dict) -> ChecklistItem:
    item_type = ChecklistItem.TYPE_ANOMALY
    if res["rule_id"] in ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "M"] or res["missing_support"]:
        item_type = ChecklistItem.TYPE_MISSING_DOCUMENT
    elif res["rule_id"] == "N":
        item_type = ChecklistItem.TYPE_WARNING
        
    rec_doc = None
    if res["missing_support"]:
        rec_doc = ", ".join(res["missing_support"])
    elif res["evidence_document"]:
        rec_doc = f"Check {res['evidence_document']}"
        
    description = res["evidence_text"] or f"Anomaly flagged by rule {res['rule_id']}: {res['rule_name']}"
    
    return ChecklistItem(
        tax_job_id=job_id,
        type=item_type,
        title=res["rule_name"],
        description=description,
        severity=res["severity"],
        status=ChecklistItem.STATUS_OPEN,
        source_file=res["evidence_document"],
        recommended_document=rec_doc,
        email_text=res["recommended_action"],
        rule_id=res["rule_id"],
        category=res["category"],
        confidence_score=res["confidence_score"],
        extracted_amount=res["extracted_amount"],
        expected_amount=res["expected_amount"],
        difference=res["difference"],
        tolerance=res["tolerance"],
        missing_support=res["missing_support"]
    )

def check_rule_A(job, doc_types, extracted_vals, files, all_text_lower):
    missing = "PRIOR_YEAR_RETURN" not in doc_types
    status = "FLAGGED" if missing else "PASSED"
    return make_anomaly_result(
        rule_id="A",
        rule_name="Prior Year Tax Return Missing",
        category="CORE_MISSING_DOCUMENT",
        severity="HIGH",
        status=status,
        return_type=job.return_type,
        evidence_text="No prior year tax return (Form 1120-S, 1065, or 1040) was detected in the upload inventory." if missing else None,
        missing_support=["PRIOR_YEAR_RETURN"] if missing else [],
        recommended_action="Please provide the prior year federal tax return so we can verify entity details and carryforward balances.",
        review_required_by="TAX_PREPARER"
    )

def check_rule_B(job, doc_types, extracted_vals, files, all_text_lower):
    missing = "BALANCE_SHEET" not in doc_types
    status = "FLAGGED" if missing else "PASSED"
    return make_anomaly_result(
        rule_id="B",
        rule_name="Balance Sheet Missing",
        category="CORE_MISSING_DOCUMENT",
        severity="HIGH",
        status=status,
        return_type=job.return_type,
        evidence_text="No current year balance sheet was detected in the document inventory." if missing else None,
        missing_support=["BALANCE_SHEET"] if missing else [],
        recommended_action="Please provide the current year balance sheet so we can reconcile asset, liability, and equity accounts.",
        review_required_by="TAX_PREPARER"
    )

def check_rule_C(job, doc_types, extracted_vals, files, all_text_lower):
    missing = "INCOME_STATEMENT" not in doc_types
    status = "FLAGGED" if missing else "PASSED"
    return make_anomaly_result(
        rule_id="C",
        rule_name="Income Statement Missing",
        category="CORE_MISSING_DOCUMENT",
        severity="HIGH",
        status=status,
        return_type=job.return_type,
        evidence_text="No current year income statement or profit & loss (P&L) was detected." if missing else None,
        missing_support=["INCOME_STATEMENT"] if missing else [],
        recommended_action="Please provide the current year profit & loss statement so we can audit revenue and business expenses.",
        review_required_by="TAX_PREPARER"
    )

def check_rule_D(job, doc_types, extracted_vals, files, all_text_lower):
    can_run, reason = check_rule_preconditions(
        required_documents=["BALANCE_SHEET", "INCOME_STATEMENT"],
        uploaded_doc_types=doc_types
    )
    if not can_run:
        return make_anomaly_result(
            rule_id="D",
            rule_name="Trial Balance Missing",
            category="CORE_MISSING_DOCUMENT",
            severity="HIGH",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason=reason
        )
    missing = "TRIAL_BALANCE" not in doc_types
    status = "FLAGGED" if missing else "PASSED"
    return make_anomaly_result(
        rule_id="D",
        rule_name="Trial Balance Missing",
        category="CORE_MISSING_DOCUMENT",
        severity="HIGH",
        status=status,
        return_type=job.return_type,
        evidence_text="Balance sheet and income statement were found, but no account-level trial balance was detected." if missing else None,
        missing_support=["TRIAL_BALANCE"] if missing else [],
        recommended_action="Please provide the current year trial balance so we can verify account-level balances and classifications.",
        review_required_by="TAX_PREPARER"
    )

def check_rule_E(job, doc_types, extracted_vals, files, all_text_lower):
    has_tb_or_bs = "TRIAL_BALANCE" in doc_types or "BALANCE_SHEET" in doc_types
    if not has_tb_or_bs:
        return make_anomaly_result(
            rule_id="E",
            rule_name="General Ledger Detail Missing",
            category="CORE_MISSING_DOCUMENT",
            severity="MEDIUM",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason="Rule runs only if Trial Balance or Balance Sheet is present."
        )
    missing = "GENERAL_LEDGER" not in doc_types
    status = "FLAGGED" if missing else "PASSED"
    return make_anomaly_result(
        rule_id="E",
        rule_name="General Ledger Detail Missing",
        category="CORE_MISSING_DOCUMENT",
        severity="MEDIUM",
        status=status,
        return_type=job.return_type,
        evidence_text="Financial reports are present, but the general ledger containing transactional entries is missing." if missing else None,
        missing_support=["GENERAL_LEDGER"] if missing else [],
        recommended_action="Please provide the transaction-level general ledger detail report to support auditing classifications.",
        review_required_by="TAX_PREPARER"
    )

def check_rule_F(job, doc_types, extracted_vals, files, all_text_lower):
    kws = ["wages", "payroll", "salaries", "officer compensation"]
    has_keywords = any(w in all_text_lower for w in kws)
    if not has_keywords:
        return make_anomaly_result(
            rule_id="F",
            rule_name="Payroll Support Missing",
            category="PAYROLL_SUPPORT",
            severity="HIGH",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason="No payroll keywords detected in uploaded documents."
        )
    
    missing = "PAYROLL_SUMMARY" not in doc_types and "W2_W3" not in doc_types
    status = "FLAGGED" if missing else "PASSED"
    
    evidence_text = None
    evidence_doc = None
    if missing:
        for job_file in files:
            txt_path = os.path.join(os.getcwd(), job_file.file_path + ".txt")
            if os.path.exists(txt_path):
                try:
                    with open(txt_path, "r", encoding="utf-8") as f:
                        text = f.read()
                    for line in text.split("\n"):
                        if any(kw in line.lower() for kw in kws):
                            evidence_text = f"Found payroll term in {job_file.file_name}: '{line.strip()}'"
                            evidence_doc = job_file.file_name
                            break
                    if evidence_text:
                        break
                except Exception:
                    pass
        if not evidence_text:
            evidence_text = "Payroll or salary expense entries were detected, but no supporting payroll summary, W-2, or W-3 reports were uploaded."
            
    return make_anomaly_result(
        rule_id="F",
        rule_name="Payroll Support Missing",
        category="PAYROLL_SUPPORT",
        severity="HIGH",
        status=status,
        return_type=job.return_type,
        evidence_document=evidence_doc,
        evidence_text=evidence_text if missing else None,
        missing_support=["PAYROLL_SUMMARY", "W2_W3"] if missing else [],
        recommended_action="Please provide the annual payroll summary, W-2/W-3 reports, or quarterly payroll tax filings to substantiate employee compensation expenses.",
        review_required_by="TAX_PREPARER"
    )

def check_rule_G(job, doc_types, extracted_vals, files, all_text_lower):
    kws = ["depreciation", "fixed assets", "accumulated depreciation", "depreciation expense"]
    has_keywords = any(w in all_text_lower for w in kws)
    if not has_keywords:
        return make_anomaly_result(
            rule_id="G",
            rule_name="Depreciation Schedule Missing",
            category="DEPRECIATION_SUPPORT",
            severity="MEDIUM",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason="No depreciation keywords detected in uploaded documents."
        )
    
    missing = "DEPRECIATION_SCHEDULE" not in doc_types
    status = "FLAGGED" if missing else "PASSED"
    
    evidence_text = None
    evidence_doc = None
    if missing:
        for job_file in files:
            txt_path = os.path.join(os.getcwd(), job_file.file_path + ".txt")
            if os.path.exists(txt_path):
                try:
                    with open(txt_path, "r", encoding="utf-8") as f:
                        text = f.read()
                    for line in text.split("\n"):
                        if any(kw in line.lower() for kw in kws):
                            evidence_text = f"Found depreciation term in {job_file.file_name}: '{line.strip()}'"
                            evidence_doc = job_file.file_name
                            break
                    if evidence_text:
                        break
                except Exception:
                    pass
        if not evidence_text:
            evidence_text = "Depreciation expenses or fixed asset items were found, but the supporting asset depreciation schedule is missing."
            
    return make_anomaly_result(
        rule_id="G",
        rule_name="Depreciation Schedule Missing",
        category="DEPRECIATION_SUPPORT",
        severity="MEDIUM",
        status=status,
        return_type=job.return_type,
        evidence_document=evidence_doc,
        evidence_text=evidence_text if missing else None,
        missing_support=["DEPRECIATION_SCHEDULE"] if missing else [],
        recommended_action="Please provide the detailed fixed asset and depreciation schedule so we can reconcile tax depreciation adjustments.",
        review_required_by="TAX_PREPARER"
    )

def check_rule_H(job, doc_types, extracted_vals, files, all_text_lower):
    kws = ["loan", "interest expense", "notes payable", "mortgage", "lender"]
    has_keywords = any(w in all_text_lower for w in kws)
    if not has_keywords:
        return make_anomaly_result(
            rule_id="H",
            rule_name="Loan / Interest Statement Missing",
            category="LOAN_SUPPORT",
            severity="MEDIUM",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason="No loan/interest keywords detected in uploaded documents."
        )
    
    missing = "LOAN_STATEMENT" not in doc_types
    status = "FLAGGED" if missing else "PASSED"
    
    evidence_text = None
    evidence_doc = None
    if missing:
        for job_file in files:
            txt_path = os.path.join(os.getcwd(), job_file.file_path + ".txt")
            if os.path.exists(txt_path):
                try:
                    with open(txt_path, "r", encoding="utf-8") as f:
                        text = f.read()
                    for line in text.split("\n"):
                        if any(kw in line.lower() for kw in kws):
                            evidence_text = f"Found loan term in {job_file.file_name}: '{line.strip()}'"
                            evidence_doc = job_file.file_name
                            break
                    if evidence_text:
                        break
                except Exception:
                    pass
        if not evidence_text:
            evidence_text = "Loan liabilities or interest expenses were detected, but no lender statements were provided."
            
    return make_anomaly_result(
        rule_id="H",
        rule_name="Loan / Interest Statement Missing",
        category="LOAN_SUPPORT",
        severity="MEDIUM",
        status=status,
        return_type=job.return_type,
        evidence_document=evidence_doc,
        evidence_text=evidence_text if missing else None,
        missing_support=["LOAN_STATEMENT"] if missing else [],
        recommended_action="Please provide year-end statements or loan agreements showing interest breakdowns and outstanding balances.",
        review_required_by="TAX_PREPARER"
    )

def check_rule_I(job, doc_types, extracted_vals, files, all_text_lower):
    kws = ["cash", "bank account", "checking account", "savings account"]
    has_keywords = any(w in all_text_lower for w in kws)
    if not has_keywords:
        return make_anomaly_result(
            rule_id="I",
            rule_name="Bank Statement Missing",
            category="BANK_SUPPORT",
            severity="HIGH",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason="No bank/cash keywords detected in uploaded documents."
        )
    
    missing = "BANK_STATEMENT" not in doc_types
    status = "FLAGGED" if missing else "PASSED"
    
    evidence_text = None
    evidence_doc = None
    if missing:
        for job_file in files:
            txt_path = os.path.join(os.getcwd(), job_file.file_path + ".txt")
            if os.path.exists(txt_path):
                try:
                    with open(txt_path, "r", encoding="utf-8") as f:
                        text = f.read()
                    for line in text.split("\n"):
                        if any(kw in line.lower() for kw in kws):
                            evidence_text = f"Found bank term in {job_file.file_name}: '{line.strip()}'"
                            evidence_doc = job_file.file_name
                            break
                    if evidence_text:
                        break
                except Exception:
                    pass
        if not evidence_text:
            evidence_text = "Cash accounts or banking transactions were detected, but no December bank statements or reconciliation worksheets exist."
            
    return make_anomaly_result(
        rule_id="I",
        rule_name="Bank Statement Missing",
        category="BANK_SUPPORT",
        severity="HIGH",
        status=status,
        return_type=job.return_type,
        evidence_document=evidence_doc,
        evidence_text=evidence_text if missing else None,
        missing_support=["BANK_STATEMENT"] if missing else [],
        recommended_action="Please provide December bank statements and reconciliation reports for all active cash accounts.",
        review_required_by="TAX_PREPARER"
    )

def check_rule_J(job, doc_types, extracted_vals, files, all_text_lower):
    kws = ["accounts receivable", "trade receivables", "customer receivables", "receivables", "a/r"]
    has_keywords = any(w in all_text_lower for w in kws)
    if not has_keywords:
        return make_anomaly_result(
            rule_id="J",
            rule_name="Accounts Receivable Aging Missing",
            category="AR_SUPPORT",
            severity="MEDIUM",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason="No accounts receivable keywords detected in uploaded documents."
        )
    
    missing = "AR_AGING" not in doc_types
    status = "FLAGGED" if missing else "PASSED"
    
    evidence_text = None
    evidence_doc = None
    if missing:
        for job_file in files:
            txt_path = os.path.join(os.getcwd(), job_file.file_path + ".txt")
            if os.path.exists(txt_path):
                try:
                    with open(txt_path, "r", encoding="utf-8") as f:
                        text = f.read()
                    for line in text.split("\n"):
                        if any(kw in line.lower() for kw in kws):
                            evidence_text = f"Found A/R term in {job_file.file_name}: '{line.strip()}'"
                            evidence_doc = job_file.file_name
                            break
                    if evidence_text:
                        break
                except Exception:
                    pass
        if not evidence_text:
            evidence_text = "Accounts receivable balances were detected, but no supporting accounts receivable (AR) aging report was uploaded."
            
    return make_anomaly_result(
        rule_id="J",
        rule_name="Accounts Receivable Aging Missing",
        category="AR_SUPPORT",
        severity="MEDIUM",
        status=status,
        return_type=job.return_type,
        evidence_document=evidence_doc,
        evidence_text=evidence_text if missing else None,
        missing_support=["AR_AGING"] if missing else [],
        recommended_action="Please provide the accounts receivable (AR) aging report as of year-end to support the trade receivables balance.",
        review_required_by="TAX_PREPARER"
    )

def check_rule_K(job, doc_types, extracted_vals, files, all_text_lower):
    kws = ["accounts payable", "payables", "trade payables", "trade creditors", "a/p"]
    has_keywords = any(w in all_text_lower for w in kws)
    if not has_keywords:
        return make_anomaly_result(
            rule_id="K",
            rule_name="Accounts Payable Aging Missing",
            category="AP_SUPPORT",
            severity="MEDIUM",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason="No accounts payable keywords detected in uploaded documents."
        )
    
    missing = "AP_AGING" not in doc_types
    status = "FLAGGED" if missing else "PASSED"
    
    evidence_text = None
    evidence_doc = None
    if missing:
        for job_file in files:
            txt_path = os.path.join(os.getcwd(), job_file.file_path + ".txt")
            if os.path.exists(txt_path):
                try:
                    with open(txt_path, "r", encoding="utf-8") as f:
                        text = f.read()
                    for line in text.split("\n"):
                        if any(kw in line.lower() for kw in kws):
                            evidence_text = f"Found A/P term in {job_file.file_name}: '{line.strip()}'"
                            evidence_doc = job_file.file_name
                            break
                    if evidence_text:
                        break
                except Exception:
                    pass
        if not evidence_text:
            evidence_text = "Accounts payable balances were detected, but no supporting accounts payable (AP) aging report was uploaded."
            
    return make_anomaly_result(
        rule_id="K",
        rule_name="Accounts Payable Aging Missing",
        category="AP_SUPPORT",
        severity="MEDIUM",
        status=status,
        return_type=job.return_type,
        evidence_document=evidence_doc,
        evidence_text=evidence_text if missing else None,
        missing_support=["AP_AGING"] if missing else [],
        recommended_action="Please provide the accounts payable (AP) aging report as of year-end to support the trade payables balance.",
        review_required_by="TAX_PREPARER"
    )

def check_rule_L(job, doc_types, extracted_vals, files, all_text_lower):
    detected_misc_val = 0.0
    evidence_text = None
    evidence_doc = None
    for job_file in files:
        txt_path = os.path.join(os.getcwd(), job_file.file_path + ".txt")
        if os.path.exists(txt_path):
            try:
                with open(txt_path, "r", encoding="utf-8") as f:
                    text_content = f.read()
                for line in text_content.split("\n"):
                    line_lower = line.lower()
                    if ("miscellaneous" in line_lower or "misc" in line_lower) and ("expense" in line_lower or "expenses" in line_lower or "deduction" in line_lower):
                        val = extract_numeric_value(line)
                        if val is not None:
                            detected_misc_val = abs(val)
                            evidence_text = f"Miscellaneous expenses of ${detected_misc_val:,.2f} detected: '{line.strip()}'"
                            evidence_doc = job_file.file_name
                            break
                if evidence_text:
                    break
            except Exception:
                pass

    if not evidence_text:
        return make_anomaly_result(
            rule_id="L",
            rule_name="High Miscellaneous Expense",
            category="FINANCIAL_MATHEMATICAL",
            severity="MEDIUM",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason="No miscellaneous expenses detected in documents."
        )

    gross_receipts = extracted_vals.get("gross_receipts", 0.0)
    limit = 10000.00
    misc_exceeds = detected_misc_val > limit or (gross_receipts > 0 and (detected_misc_val / gross_receipts) > 0.02)
    
    status = "FLAGGED" if misc_exceeds else "PASSED"
    
    diff = None
    if detected_misc_val > limit:
        diff = detected_misc_val - limit
        
    return make_anomaly_result(
        rule_id="L",
        rule_name="High Miscellaneous Expense",
        category="FINANCIAL_MATHEMATICAL",
        severity="MEDIUM",
        status=status,
        return_type=job.return_type,
        evidence_document=evidence_doc,
        evidence_text=evidence_text if misc_exceeds else None,
        extracted_amount=detected_misc_val,
        expected_amount=limit,
        difference=diff,
        tolerance=limit,
        recommended_action="Please provide a detailed general ledger breakdown or transaction list for miscellaneous expenses, as they exceed our review threshold.",
        review_required_by="TAX_PREPARER"
    )

def check_rule_M(job, doc_types, extracted_vals, files, all_text_lower):
    kws = [
        "shareholder distribution", "shareholder distributions", "partner distribution", 
        "partner distributions", "owner draw", "owner draws", "officer draw", "officer draws", 
        "shareholder draw", "shareholder draws", "due from shareholder", "due from officer", 
        "loan to shareholder", "loan to officer", "capital distribution"
    ]
    has_keywords = any(w in all_text_lower for w in kws)
    if not has_keywords:
        return make_anomaly_result(
            rule_id="M",
            rule_name="Shareholder Distribution Support Missing",
            category="OWNER_PARTNER_TRANSACTIONS",
            severity="MEDIUM",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason="No distribution/draw keywords detected in uploaded documents."
        )
    
    missing = "SHAREHOLDER_DISTRIBUTION" not in doc_types and "PARTNER_DISTRIBUTION" not in doc_types
    status = "FLAGGED" if missing else "PASSED"
    
    evidence_text = None
    evidence_doc = None
    if missing:
        for job_file in files:
            txt_path = os.path.join(os.getcwd(), job_file.file_path + ".txt")
            if os.path.exists(txt_path):
                try:
                    with open(txt_path, "r", encoding="utf-8") as f:
                        text = f.read()
                    for line in text.split("\n"):
                        if any(kw in line.lower() for kw in kws):
                            evidence_text = f"Found distribution term in {job_file.file_name}: '{line.strip()}'"
                            evidence_doc = job_file.file_name
                            break
                    if evidence_text:
                        break
                except Exception:
                    pass
        if not evidence_text:
            evidence_text = "Shareholder distributions, draws, or officer cash advances were detected, but no supporting distribution schedule or ledger details were provided."
            
    return make_anomaly_result(
        rule_id="M",
        rule_name="Shareholder Distribution Support Missing",
        category="OWNER_PARTNER_TRANSACTIONS",
        severity="MEDIUM",
        status=status,
        return_type=job.return_type,
        evidence_document=evidence_doc,
        evidence_text=evidence_text if missing else None,
        missing_support=["SHAREHOLDER_DISTRIBUTION", "PARTNER_DISTRIBUTION"] if missing else [],
        recommended_action="Please provide documentation or ledger details for shareholder distributions, draws, or owner transactions to verify tax treatment.",
        review_required_by="TAX_PREPARER"
    )

def check_rule_N(job, doc_types, extracted_vals, files, all_text_lower):
    negative_alerts = []
    for val_key, val_amount in extracted_vals.items():
        if val_amount is not None:
            if val_key in ["cash_ending", "accounts_receivable_ending", "inventory_ending", "fixed_assets_cost"] and val_amount < 0:
                negative_alerts.append(f"{val_key.replace('_', ' ').title()} ({val_amount:,.2f}) is negative.")
            elif val_key in ["accumulated_depreciation"] and val_amount > 0:
                negative_alerts.append(f"{val_key.replace('_', ' ').title()} ({val_amount:,.2f}) is positive (contra-asset should be negative).")
            
    if not negative_alerts:
        return make_anomaly_result(
            rule_id="N",
            rule_name="Account Balance Sign Warning",
            category="FINANCIAL_MATHEMATICAL",
            severity="LOW",
            status="PASSED",
            return_type=job.return_type
        )
        
    evidence_text = "Unusual account balances detected: " + "; ".join(negative_alerts)
    return make_anomaly_result(
        rule_id="N",
        rule_name="Account Balance Sign Warning",
        category="FINANCIAL_MATHEMATICAL",
        severity="LOW",
        status="FLAGGED",
        return_type=job.return_type,
        evidence_text=evidence_text,
        recommended_action="Please check the balances of the following accounts for sign correctness: " + "; ".join(negative_alerts),
        review_required_by="TAX_PREPARER"
    )

def check_rule_BS_001(job, doc_types, extracted_vals, files, db: Session):
    bs_files = db.query(JobFile).filter(
        JobFile.tax_job_id == job.id,
        JobFile.detected_document_type == "BALANCE_SHEET"
    ).all()
    
    if not bs_files:
        return [make_anomaly_result(
            rule_id="BS-001",
            rule_name="Balance Sheet Equation Mismatch",
            category="FINANCIAL_MATHEMATICAL",
            severity="HIGH",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason="Balance Sheet document not found."
        )]
        
    results = []
    for bs_file in bs_files:
        txt_path = os.path.join(os.getcwd(), bs_file.file_path + ".txt")
        if not os.path.exists(txt_path):
            results.append(make_anomaly_result(
                rule_id="BS-001",
                rule_name="Balance Sheet Equation Mismatch",
                category="FINANCIAL_MATHEMATICAL",
                severity="HIGH",
                status="SKIPPED",
                return_type=job.return_type,
                evidence_document=bs_file.file_name,
                skip_reason="Balance Sheet text file missing."
            ))
            continue
            
        try:
            with open(txt_path, "r", encoding="utf-8") as f:
                text_content = f.read()
            
            assets, liabilities, equity = analyze_balance_sheet(text_content)
            if assets is None or liabilities is None or equity is None:
                missing_vals = []
                if assets is None: missing_vals.append("Assets")
                if liabilities is None: missing_vals.append("Liabilities")
                if equity is None: missing_vals.append("Equity")
                results.append(make_anomaly_result(
                    rule_id="BS-001",
                    rule_name="Balance Sheet Equation Mismatch",
                    category="FINANCIAL_MATHEMATICAL",
                    severity="HIGH",
                    status="SKIPPED",
                    return_type=job.return_type,
                    evidence_document=bs_file.file_name,
                    skip_reason=f"Could not extract balance sheet values: missing {', '.join(missing_vals)}."
                ))
                continue
                
            tie_out = check_tie_out(assets, liabilities + equity)
            status = "PASSED" if tie_out["passed"] else "FLAGGED"
            
            evidence_text = f"Mathematical discrepancy in balance sheet '{bs_file.file_name}': Assets (${assets:,.2f}) != Liabilities (${liabilities:,.2f}) + Equity (${equity:,.2f}). Mismatch is ${tie_out['difference']:,.2f}."
            
            results.append(make_anomaly_result(
                rule_id="BS-001",
                rule_name="Balance Sheet Equation Mismatch",
                category="FINANCIAL_MATHEMATICAL",
                severity="HIGH",
                status=status,
                return_type=job.return_type,
                evidence_document=bs_file.file_name,
                evidence_text=evidence_text if not tie_out["passed"] else None,
                extracted_amount=assets,
                expected_amount=liabilities + equity,
                difference=tie_out["difference"],
                tolerance=tie_out["tolerance"],
                recommended_action=f"Please reconcile the balance sheet since the balance sheet equation does not balance: Assets (${assets:,.2f}) != Liabilities (${liabilities:,.2f}) + Equity (${equity:,.2f}).",
                review_required_by="TAX_PREPARER"
            ))
        except Exception as e:
            results.append(make_anomaly_result(
                rule_id="BS-001",
                rule_name="Balance Sheet Equation Mismatch",
                category="FINANCIAL_MATHEMATICAL",
                severity="HIGH",
                status="SKIPPED",
                return_type=job.return_type,
                evidence_document=bs_file.file_name,
                skip_reason=f"Error checking BS math: {str(e)}"
            ))
            
    return results

def check_rule_PY_001(job, doc_types, extracted_vals, files, db: Session):
    can_run, reason = check_rule_preconditions(
        required_documents=["PRIOR_YEAR_RETURN"],
        required_values=["total_assets_beginning"],
        uploaded_doc_types=doc_types,
        extracted_values=extracted_vals
    )
    if not can_run:
        return make_anomaly_result(
            rule_id="PY-001",
            rule_name="Beginning Balance Mismatch",
            category="PRIOR_YEAR_ROLL_FORWARD",
            severity="HIGH",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason=reason
        )
        
    py_assets = None
    py_files = db.query(JobFile).filter(JobFile.tax_job_id == job.id, JobFile.detected_document_type == "PRIOR_YEAR_RETURN").all()
    evidence_doc = None
    for py_file in py_files:
        py_txt_path = os.path.join(os.getcwd(), py_file.file_path + ".txt")
        if os.path.exists(py_txt_path):
            try:
                with open(py_txt_path, "r", encoding="utf-8") as f:
                    py_text = f.read()
                py_metrics = harvest_financial_metrics_regex(py_text)
                if "total_assets_ending" in py_metrics:
                    py_assets = py_metrics["total_assets_ending"]
                    evidence_doc = py_file.file_name
                    break
            except Exception:
                pass
                
    if py_assets is None:
        return make_anomaly_result(
            rule_id="PY-001",
            rule_name="Beginning Balance Mismatch",
            category="PRIOR_YEAR_ROLL_FORWARD",
            severity="HIGH",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason="Could not extract ending total assets from prior year return."
        )
        
    cy_beg_assets = extracted_vals["total_assets_beginning"]
    tie_out = check_tie_out(cy_beg_assets, py_assets)
    status = "PASSED" if tie_out["passed"] else "FLAGGED"
    
    evidence_text = f"Beginning total assets (${cy_beg_assets:,.2f}) do not match prior year ending total assets (${py_assets:,.2f}). Difference is ${tie_out['difference']:,.2f}."
    
    return make_anomaly_result(
        rule_id="PY-001",
        rule_name="Beginning Balance Mismatch",
        category="PRIOR_YEAR_ROLL_FORWARD",
        severity="HIGH",
        status=status,
        return_type=job.return_type,
        evidence_document=evidence_doc,
        evidence_text=evidence_text if not tie_out["passed"] else None,
        extracted_amount=cy_beg_assets,
        expected_amount=py_assets,
        difference=tie_out["difference"],
        tolerance=tie_out["tolerance"],
        recommended_action=f"Please reconcile beginning assets (${cy_beg_assets:,.2f}) with prior ending assets (${py_assets:,.2f}), as a mismatch of ${tie_out['difference']:,.2f} was detected.",
        review_required_by="TAX_PREPARER"
    )

def check_rule_PY_002(job, doc_types, extracted_vals, files):
    if job.return_type not in ["1120", "1120-S"]:
        return make_anomaly_result(
            rule_id="PY-002",
            rule_name="Retained Earnings Rollforward Mismatch",
            category="PRIOR_YEAR_ROLL_FORWARD",
            severity="HIGH",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason="Rule only applies to 1120 and 1120-S returns."
        )
        
    can_run, reason = check_rule_preconditions(
        required_values=["retained_earnings_beginning", "retained_earnings_ending", "net_income"],
        extracted_values=extracted_vals
    )
    if not can_run:
        return make_anomaly_result(
            rule_id="PY-002",
            rule_name="Retained Earnings Rollforward Mismatch",
            category="PRIOR_YEAR_ROLL_FORWARD",
            severity="HIGH",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason=reason
        )
        
    beg_re = extracted_vals["retained_earnings_beginning"]
    end_re = extracted_vals["retained_earnings_ending"]
    net_inc = extracted_vals["net_income"]
    dist = extracted_vals.get("shareholder_distributions", 0.0) or extracted_vals.get("partner_distributions", 0.0) or 0.0
    
    expected_end_re = beg_re + net_inc - dist
    tie_out = check_tie_out(end_re, expected_end_re)
    status = "PASSED" if tie_out["passed"] else "FLAGGED"
    
    evidence_text = f"Retained earnings rollforward discrepancy: Beginning RE (${beg_re:,.2f}) + Net Income (${net_inc:,.2f}) - Distributions (${dist:,.2f}) = Expected Ending RE (${expected_end_re:,.2f}) != Actual Ending RE (${end_re:,.2f}). Mismatch is ${tie_out['difference']:,.2f}."
    
    return make_anomaly_result(
        rule_id="PY-002",
        rule_name="Retained Earnings Rollforward Mismatch",
        category="PRIOR_YEAR_ROLL_FORWARD",
        severity="HIGH",
        status=status,
        return_type=job.return_type,
        evidence_text=evidence_text if not tie_out["passed"] else None,
        extracted_amount=end_re,
        expected_amount=expected_end_re,
        difference=tie_out["difference"],
        tolerance=tie_out["tolerance"],
        recommended_action=f"Please review the retained earnings rollforward, as there is an unreconciled difference of ${tie_out['difference']:,.2f}.",
        review_required_by="TAX_PREPARER"
    )

def check_rule_BST_001(job, doc_types, extracted_vals, files, db: Session):
    can_run = "BANK_STATEMENT" in doc_types or "BANK_RECONCILIATION" in doc_types
    if not can_run:
        return make_anomaly_result(
            rule_id="BST-001",
            rule_name="Cash Per Books vs Bank Mismatch",
            category="BALANCE_SHEET_TIE_OUT",
            severity="HIGH",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason="Bank Statement or Bank Reconciliation document not found."
        )
        
    can_run_vals, reason = check_rule_preconditions(
        required_values=["cash_ending"],
        extracted_values=extracted_vals
    )
    if not can_run_vals:
        return make_anomaly_result(
            rule_id="BST-001",
            rule_name="Cash Per Books vs Bank Mismatch",
            category="BALANCE_SHEET_TIE_OUT",
            severity="HIGH",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason=reason
        )
        
    bank_ending = None
    bank_files = db.query(JobFile).filter(
        JobFile.tax_job_id == job.id,
        JobFile.detected_document_type.in_(["BANK_STATEMENT", "BANK_RECONCILIATION"])
    ).all()
    evidence_doc = None
    for b_file in bank_files:
        b_txt_path = os.path.join(os.getcwd(), b_file.file_path + ".txt")
        if os.path.exists(b_txt_path):
            try:
                with open(b_txt_path, "r", encoding="utf-8") as f:
                    b_text = f.read()
                for line in b_text.split("\n"):
                     line_lower = line.lower()
                     if "ending balance" in line_lower or "statement ending" in line_lower or "closing balance" in line_lower:
                         val = extract_numeric_value(line)
                         if val is not None:
                             bank_ending = val
                             evidence_doc = b_file.file_name
                             break
                if bank_ending is not None:
                    break
            except Exception:
                pass
                
    if bank_ending is None:
        return make_anomaly_result(
            rule_id="BST-001",
            rule_name="Cash Per Books vs Bank Mismatch",
            category="BALANCE_SHEET_TIE_OUT",
            severity="HIGH",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason="Could not extract ending balance from bank statements."
        )
        
    cash_books = extracted_vals["cash_ending"]
    tie_out = check_tie_out(cash_books, bank_ending)
    status = "PASSED" if tie_out["passed"] else "FLAGGED"
    
    evidence_text = f"Cash per books (${cash_books:,.2f}) does not match bank statement ending balance (${bank_ending:,.2f}). Difference is ${tie_out['difference']:,.2f}."
    
    return make_anomaly_result(
        rule_id="BST-001",
        rule_name="Cash Per Books vs Bank Mismatch",
        category="BALANCE_SHEET_TIE_OUT",
        severity="HIGH",
        status=status,
        return_type=job.return_type,
        evidence_document=evidence_doc,
        evidence_text=evidence_text if not tie_out["passed"] else None,
        extracted_amount=cash_books,
        expected_amount=bank_ending,
        difference=tie_out["difference"],
        tolerance=tie_out["tolerance"],
        recommended_action=f"Please provide the bank reconciliation statement for the checking/cash accounts to explain the ${tie_out['difference']:,.2f} mismatch.",
        review_required_by="TAX_PREPARER"
    )

def check_rule_BST_002(job, doc_types, extracted_vals, files, db: Session):
    can_run, reason = check_rule_preconditions(
        required_documents=["AR_AGING"],
        required_values=["accounts_receivable_ending"],
        uploaded_doc_types=doc_types,
        extracted_values=extracted_vals
    )
    if not can_run:
        return make_anomaly_result(
            rule_id="BST-002",
            rule_name="AR Aging Tie-Out Mismatch",
            category="BALANCE_SHEET_TIE_OUT",
            severity="MEDIUM",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason=reason
        )
        
    ar_aging_total = None
    ar_files = db.query(JobFile).filter(JobFile.tax_job_id == job.id, JobFile.detected_document_type == "AR_AGING").all()
    evidence_doc = None
    for ar_file in ar_files:
        ar_txt_path = os.path.join(os.getcwd(), ar_file.file_path + ".txt")
        if os.path.exists(ar_txt_path):
            try:
                with open(ar_txt_path, "r", encoding="utf-8") as f:
                    ar_text = f.read()
                for line in ar_text.split("\n"):
                     line_lower = line.lower()
                     if "total" in line_lower or "balance" in line_lower:
                         val = extract_numeric_value(line)
                         if val is not None:
                             ar_aging_total = val
                             evidence_doc = ar_file.file_name
            except Exception:
                pass
                
    if ar_aging_total is None:
        return make_anomaly_result(
            rule_id="BST-002",
            rule_name="AR Aging Tie-Out Mismatch",
            category="BALANCE_SHEET_TIE_OUT",
            severity="MEDIUM",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason="Could not extract total from AR aging report."
        )
        
    ar_books = extracted_vals["accounts_receivable_ending"]
    tie_out = check_tie_out(ar_books, ar_aging_total)
    status = "PASSED" if tie_out["passed"] else "FLAGGED"
    
    evidence_text = f"Accounts receivable per books (${ar_books:,.2f}) does not match AR aging total (${ar_aging_total:,.2f}). Difference is ${tie_out['difference']:,.2f}."
    
    return make_anomaly_result(
        rule_id="BST-002",
        rule_name="AR Aging Tie-Out Mismatch",
        category="BALANCE_SHEET_TIE_OUT",
        severity="MEDIUM",
        status=status,
        return_type=job.return_type,
        evidence_document=evidence_doc,
        evidence_text=evidence_text if not tie_out["passed"] else None,
        extracted_amount=ar_books,
        expected_amount=ar_aging_total,
        difference=tie_out["difference"],
        tolerance=tie_out["tolerance"],
        recommended_action=f"Please reconcile the accounts receivable aging report with the balance sheet, as there is a mismatch of ${tie_out['difference']:,.2f}.",
        review_required_by="TAX_PREPARER"
    )

def check_rule_BST_003(job, doc_types, extracted_vals, files, db: Session):
    can_run, reason = check_rule_preconditions(
        required_documents=["AP_AGING"],
        required_values=["accounts_payable_ending"],
        uploaded_doc_types=doc_types,
        extracted_values=extracted_vals
    )
    if not can_run:
        return make_anomaly_result(
            rule_id="BST-003",
            rule_name="AP Aging Tie-Out Mismatch",
            category="BALANCE_SHEET_TIE_OUT",
            severity="MEDIUM",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason=reason
        )
        
    ap_aging_total = None
    ap_files = db.query(JobFile).filter(JobFile.tax_job_id == job.id, JobFile.detected_document_type == "AP_AGING").all()
    evidence_doc = None
    for ap_file in ap_files:
        ap_txt_path = os.path.join(os.getcwd(), ap_file.file_path + ".txt")
        if os.path.exists(ap_txt_path):
            try:
                with open(ap_txt_path, "r", encoding="utf-8") as f:
                    ap_text = f.read()
                for line in ap_text.split("\n"):
                     line_lower = line.lower()
                     if "total" in line_lower or "balance" in line_lower:
                         val = extract_numeric_value(line)
                         if val is not None:
                             ap_aging_total = val
                             evidence_doc = ap_file.file_name
            except Exception:
                pass
                
    if ap_aging_total is None:
        return make_anomaly_result(
            rule_id="BST-003",
            rule_name="AP Aging Tie-Out Mismatch",
            category="BALANCE_SHEET_TIE_OUT",
            severity="MEDIUM",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason="Could not extract total from AP aging report."
        )
        
    ap_books = extracted_vals["accounts_payable_ending"]
    tie_out = check_tie_out(ap_books, ap_aging_total)
    status = "PASSED" if tie_out["passed"] else "FLAGGED"
    
    evidence_text = f"Accounts payable per books (${ap_books:,.2f}) does not match AP aging total (${ap_aging_total:,.2f}). Difference is ${tie_out['difference']:,.2f}."
    
    return make_anomaly_result(
        rule_id="BST-003",
        rule_name="AP Aging Tie-Out Mismatch",
        category="BALANCE_SHEET_TIE_OUT",
        severity="MEDIUM",
        status=status,
        return_type=job.return_type,
        evidence_document=evidence_doc,
        evidence_text=evidence_text if not tie_out["passed"] else None,
        extracted_amount=ap_books,
        expected_amount=ap_aging_total,
        difference=tie_out["difference"],
        tolerance=tie_out["tolerance"],
        recommended_action=f"Please reconcile the accounts payable aging report with the balance sheet, as there is a mismatch of ${tie_out['difference']:,.2f}.",
        review_required_by="TAX_PREPARER"
    )

def check_rule_REV_001(job, doc_types, extracted_vals, files, db: Session):
    can_run, reason = check_rule_preconditions(
        required_documents=["FORM_1099_K"],
        required_values=["gross_receipts"],
        uploaded_doc_types=doc_types,
        extracted_values=extracted_vals
    )
    if not can_run:
        return make_anomaly_result(
            rule_id="REV-001",
            rule_name="1099-K Income Exceeds Reported Revenue",
            category="REVENUE_1099_RECONCILIATION",
            severity="HIGH",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason=reason
        )
        
    k1099_amount = None
    k1099_files = db.query(JobFile).filter(JobFile.tax_job_id == job.id, JobFile.detected_document_type == "FORM_1099_K").all()
    evidence_doc = None
    for k_file in k1099_files:
        k_txt_path = os.path.join(os.getcwd(), k_file.file_path + ".txt")
        if os.path.exists(k_txt_path):
            try:
                with open(k_txt_path, "r", encoding="utf-8") as f:
                    k_text = f.read()
                for line in k_text.split("\n"):
                     line_lower = line.lower()
                     if "gross amount" in line_lower or "card and third party" in line_lower:
                         val = extract_numeric_value(line)
                         if val is not None:
                             k1099_amount = val
                             evidence_doc = k_file.file_name
                             break
            except Exception:
                pass
                
    if k1099_amount is None:
        return make_anomaly_result(
            rule_id="REV-001",
            rule_name="1099-K Income Exceeds Reported Revenue",
            category="REVENUE_1099_RECONCILIATION",
            severity="HIGH",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason="Could not extract gross amount from Form 1099-K."
        )
        
    gross_receipts = extracted_vals["gross_receipts"]
    tie_out = check_tie_out(gross_receipts, k1099_amount, tolerance=5.0)
    
    exceeds = k1099_amount > gross_receipts + 5.0
    status = "FLAGGED" if exceeds else "PASSED"
    
    evidence_text = f"Form 1099-K reported gross card payments (${k1099_amount:,.2f}) exceed reported gross receipts (${gross_receipts:,.2f}). Difference is ${tie_out['difference']:,.2f}."
    
    return make_anomaly_result(
        rule_id="REV-001",
        rule_name="1099-K Income Exceeds Reported Revenue",
        category="REVENUE_1099_RECONCILIATION",
        severity="HIGH",
        status=status,
        return_type=job.return_type,
        evidence_document=evidence_doc,
        evidence_text=evidence_text if exceeds else None,
        extracted_amount=gross_receipts,
        expected_amount=k1099_amount,
        difference=tie_out["difference"],
        tolerance=tie_out["tolerance"],
        recommended_action="1099-K reconciliation schedule or updated sales reports",
        review_required_by="TAX_PREPARER"
    )

def check_rule_REV_002(job, doc_types, extracted_vals, files, db: Session):
    can_run = "FORM_1099_NEC" in doc_types or "FORM_1099_MISC" in doc_types
    if not can_run:
        return make_anomaly_result(
            rule_id="REV-002",
            rule_name="1099-NEC/MISC Exceeds Reported Revenue",
            category="REVENUE_1099_RECONCILIATION",
            severity="HIGH",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason="Form 1099-NEC or 1099-MISC document not found."
        )
        
    can_run_vals, reason = check_rule_preconditions(
        required_values=["gross_receipts"],
        extracted_values=extracted_vals
    )
    if not can_run_vals:
        return make_anomaly_result(
            rule_id="REV-002",
            rule_name="1099-NEC/MISC Exceeds Reported Revenue",
            category="REVENUE_1099_RECONCILIATION",
            severity="HIGH",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason=reason
        )
        
    nec_misc_total = 0.0
    nec_misc_files = db.query(JobFile).filter(
        JobFile.tax_job_id == job.id,
        JobFile.detected_document_type.in_(["FORM_1099_NEC", "FORM_1099_MISC"])
    ).all()
    
    evidence_doc = None
    for nm_file in nec_misc_files:
        nm_txt_path = os.path.join(os.getcwd(), nm_file.file_path + ".txt")
        if os.path.exists(nm_txt_path):
            try:
                with open(nm_txt_path, "r", encoding="utf-8") as f:
                    nm_text = f.read()
                for line in nm_text.split("\n"):
                     line_lower = line.lower()
                     if "nonemployee compensation" in line_lower or "compensation" in line_lower or "rents" in line_lower or "other income" in line_lower:
                         val = extract_numeric_value(line)
                         if val is not None:
                             nec_misc_total += val
                             evidence_doc = nm_file.file_name
                             break
            except Exception:
                pass
                
    if nec_misc_total == 0.0:
        return make_anomaly_result(
            rule_id="REV-002",
            rule_name="1099-NEC/MISC Exceeds Reported Revenue",
            category="REVENUE_1099_RECONCILIATION",
            severity="HIGH",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason="Could not extract nonemployee compensation or income from 1099-NEC/MISC."
        )
        
    gross_receipts = extracted_vals["gross_receipts"]
    tie_out = check_tie_out(gross_receipts, nec_misc_total, tolerance=5.0)
    
    exceeds = nec_misc_total > gross_receipts + 5.0
    status = "FLAGGED" if exceeds else "PASSED"
    
    evidence_text = f"The sum of Form 1099-NEC/MISC nonemployee compensation (${nec_misc_total:,.2f}) exceeds reported gross receipts (${gross_receipts:,.2f}). Difference is ${tie_out['difference']:,.2f}."
    
    return make_anomaly_result(
        rule_id="REV-002",
        rule_name="1099-NEC/MISC Exceeds Reported Revenue",
        category="REVENUE_1099_RECONCILIATION",
        severity="HIGH",
        status=status,
        return_type=job.return_type,
        evidence_document=evidence_doc,
        evidence_text=evidence_text if exceeds else None,
        extracted_amount=gross_receipts,
        expected_amount=nec_misc_total,
        difference=tie_out["difference"],
        tolerance=tie_out["tolerance"],
        recommended_action="1099-NEC / 1099-MISC reconciliation worksheet",
        review_required_by="TAX_PREPARER"
    )

def check_rule_PAY_002(job, doc_types, extracted_vals, files, db: Session):
    can_run = "PAYROLL_SUMMARY" in doc_types or "W2_W3" in doc_types
    if not can_run:
        return make_anomaly_result(
            rule_id="PAY-002",
            rule_name="Wages Discrepancy",
            category="PAYROLL_SUPPORT",
            severity="HIGH",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason="Payroll Summary or W-2/W-3 document not found."
        )
        
    payroll_wages = None
    payroll_files = db.query(JobFile).filter(
        JobFile.tax_job_id == job.id,
        JobFile.detected_document_type.in_(["PAYROLL_SUMMARY", "W2_W3"])
    ).all()
    
    evidence_doc = None
    for p_file in payroll_files:
        p_txt_path = os.path.join(os.getcwd(), p_file.file_path + ".txt")
        if os.path.exists(p_txt_path):
            try:
                with open(p_txt_path, "r", encoding="utf-8") as f:
                    p_text = f.read()
                for line in p_text.split("\n"):
                     line_lower = line.lower()
                     if "total wages" in line_lower or "w-3" in line_lower or "box 1" in line_lower or "gross pay" in line_lower:
                         val = extract_numeric_value(line)
                         if val is not None:
                             payroll_wages = val
                             evidence_doc = p_file.file_name
                             break
            except Exception:
                pass
                
    pnl_wages = None
    for job_file in files:
        txt_path = os.path.join(os.getcwd(), job_file.file_path + ".txt")
        if os.path.exists(txt_path):
            try:
                with open(txt_path, "r", encoding="utf-8") as f:
                    text_content = f.read()
                for line in text_content.split("\n"):
                    line_lower = line.lower()
                    if ("wages" in line_lower or "salaries" in line_lower) and not "payroll tax" in line_lower:
                        val = extract_numeric_value(line)
                        if val is not None:
                            pnl_wages = val
                            break
                if pnl_wages is not None:
                    break
            except Exception:
                pass
                
    if pnl_wages is None or payroll_wages is None:
        missing_vals = []
        if pnl_wages is None: missing_vals.append("Wages on Income Statement")
        if payroll_wages is None: missing_vals.append("Wages on Payroll Summary/W2/W3")
        return make_anomaly_result(
            rule_id="PAY-002",
            rule_name="Wages Discrepancy",
            category="PAYROLL_SUPPORT",
            severity="HIGH",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason=f"Could not extract wages: missing {', '.join(missing_vals)}."
        )
        
    tie_out = check_tie_out(pnl_wages, payroll_wages)
    status = "PASSED" if tie_out["passed"] else "FLAGGED"
    
    evidence_text = f"Wages on Income Statement (${pnl_wages:,.2f}) do not tie to Payroll Summary/W-2 total (${payroll_wages:,.2f}). Difference is ${tie_out['difference']:,.2f}."
    
    return make_anomaly_result(
        rule_id="PAY-002",
        rule_name="Wages Discrepancy",
        category="PAYROLL_SUPPORT",
        severity="HIGH",
        status=status,
        return_type=job.return_type,
        evidence_document=evidence_doc,
        evidence_text=evidence_text if not tie_out["passed"] else None,
        extracted_amount=pnl_wages,
        expected_amount=payroll_wages,
        difference=tie_out["difference"],
        tolerance=tie_out["tolerance"],
        recommended_action="Review payroll summary, W-2/W-3, and possible payroll reclassification.",
        review_required_by="TAX_PREPARER"
    )

def check_rule_RT_001(job, doc_types, extracted_vals, files, all_text_lower):
    detected_types = []
    for term, kws in RETURN_TYPE_KEYWORDS.items():
        for kw in kws:
            if kw.lower() in all_text_lower:
                detected_types.append(term)
                break
                
    if not detected_types:
        return make_anomaly_result(
            rule_id="RT-001",
            rule_name="Filing Entity Return Type Mismatch",
            category="RETURN_TYPE_ROUTING",
            severity="HIGH",
            status="PASSED",
            return_type=job.return_type
        )
        
    from collections import Counter
    strongest_match = Counter(detected_types).most_common(1)[0][0]
    
    strongest_mapped = strongest_match
    if strongest_match == "1040_SCHEDULE_C":
        strongest_mapped = "1040 / Schedule C"
        
    mismatch = job.return_type != strongest_mapped
    status = "FLAGGED" if mismatch else "PASSED"
    
    evidence_text = f"The selected return type is {job.return_type}, but uploaded documents contain signatures indicating a {strongest_mapped} entity type."
    
    return make_anomaly_result(
        rule_id="RT-001",
        rule_name="Filing Entity Return Type Mismatch",
        category="RETURN_TYPE_ROUTING",
        severity="HIGH",
        status=status,
        return_type=job.return_type,
        evidence_text=evidence_text if mismatch else None,
        recommended_action=f"Confirm correct client entity configuration. Please confirm if the target return type should be {strongest_mapped} instead of the selected {job.return_type}.",
        review_required_by="TAX_PREPARER"
    )

def check_rule_OCR_004(job, doc_types, extracted_vals, files):
    mismatch_years = set()
    evidence_doc = None
    for job_file in files:
        txt_path = os.path.join(os.getcwd(), job_file.file_path + ".txt")
        if os.path.exists(txt_path):
            try:
                with open(txt_path, "r", encoding="utf-8") as f:
                    text = f.read()
                found_years = re.findall(r'\b(20[12][0-9])\b', text)
                for y_str in found_years:
                     y = int(y_str)
                     if y != job.tax_year and y != (job.tax_year - 1):
                          mismatch_years.add(y)
                          evidence_doc = job_file.file_name
            except Exception:
                pass
                
    if not mismatch_years:
        return make_anomaly_result(
            rule_id="OCR-004",
            rule_name="Wrong Tax Year Detected",
            category="OCR_AND_DOCUMENT_QUALITY",
            severity="HIGH",
            status="PASSED",
            return_type=job.return_type
        )
        
    years_list = ", ".join(map(str, sorted(mismatch_years)))
    evidence_text = f"Documents contain mentions of tax year(s) {years_list}, which do not match the target filing year {job.tax_year}."
    
    return make_anomaly_result(
        rule_id="OCR-004",
        rule_name="Wrong Tax Year Detected",
        category="OCR_AND_DOCUMENT_QUALITY",
        severity="HIGH",
        status="FLAGGED",
        return_type=job.return_type,
        evidence_document=evidence_doc,
        evidence_text=evidence_text,
        recommended_action=f"Verify that the uploaded documents correspond to tax year {job.tax_year} and request correct tax year documents.",
        review_required_by="TAX_PREPARER"
    )

def check_rule_OCR_005(job, doc_types, extracted_vals, files):
    eins = set()
    evidence_doc = None
    for job_file in files:
        txt_path = os.path.join(os.getcwd(), job_file.file_path + ".txt")
        if os.path.exists(txt_path):
            try:
                with open(txt_path, "r", encoding="utf-8") as f:
                    text = f.read()
                found_eins = re.findall(r'\b([0-9]{2}-[0-9]{7})\b', text)
                for ein in found_eins:
                     eins.add(ein)
                     evidence_doc = job_file.file_name
            except Exception:
                pass
                
    if len(eins) <= 1:
        return make_anomaly_result(
            rule_id="OCR-005",
            rule_name="Multiple EINs Detected",
            category="OCR_AND_DOCUMENT_QUALITY",
            severity="HIGH",
            status="PASSED",
            return_type=job.return_type
        )
        
    eins_list = ", ".join(sorted(eins))
    evidence_text = f"Multiple Employer Identification Numbers (EINs) detected across uploaded files: {eins_list}. This may indicate mixed client files."
    
    return make_anomaly_result(
        rule_id="OCR-005",
        rule_name="Multiple EINs Detected",
        category="OCR_AND_DOCUMENT_QUALITY",
        severity="HIGH",
        status="FLAGGED",
        return_type=job.return_type,
        evidence_document=evidence_doc,
        evidence_text=evidence_text,
        recommended_action=f"We detected multiple EINs ({eins_list}) in your uploaded files. Please verify that all documents belong to the same entity and request correct and segregated client documents.",
        review_required_by="TAX_PREPARER"
    )

def check_rule_OWN_001(job, doc_types, extracted_vals, files):
    if job.return_type not in ["1120-S", "1065", "1120"]:
        return make_anomaly_result(
            rule_id="OWN-001",
            rule_name="Shareholder / Partner Loan Support Missing",
            category="OWNER_PARTNER_TRANSACTIONS",
            severity="MEDIUM",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason="Rule only applies to 1120-S, 1065, or 1120 returns."
        )
        
    trigger_keywords = [
        "loan to shareholder", "loan from shareholder", "due from owner", "due to owner",
        "due from partner", "due to partner", "shareholder receivable", "shareholder payable",
        "partner receivable", "partner payable", "owner loan", "member loan"
    ]
    
    has_support = any(doc in doc_types for doc in ["LOAN_STATEMENT", "SHAREHOLDER_DISTRIBUTION", "PARTNER_DISTRIBUTION", "OWNERSHIP_SCHEDULE"])
    
    triggered = False
    max_amount = 0.0
    evidence_text = None
    evidence_doc = None
    
    for job_file in files:
        txt_path = os.path.join(os.getcwd(), job_file.file_path + ".txt")
        if not os.path.exists(txt_path):
            continue
        try:
            with open(txt_path, "r", encoding="utf-8") as f:
                file_text = f.read()
            for line in file_text.split("\n"):
                line_lower = line.lower()
                for kw in trigger_keywords:
                    if kw in line_lower:
                        triggered = True
                        val = extract_numeric_value(line)
                        if val is not None:
                            val_abs = abs(val)
                            if val_abs > max_amount:
                                max_amount = val_abs
                        if not evidence_text:
                            evidence_text = f"Found loan keyword '{kw}' in {job_file.file_name}: '{line.strip()}'"
                            evidence_doc = job_file.file_name
        except Exception:
            pass
            
    if not triggered:
        return make_anomaly_result(
            rule_id="OWN-001",
            rule_name="Shareholder / Partner Loan Support Missing",
            category="OWNER_PARTNER_TRANSACTIONS",
            severity="MEDIUM",
            status="PASSED",
            return_type=job.return_type
        )
        
    if has_support:
        return make_anomaly_result(
            rule_id="OWN-001",
            rule_name="Shareholder / Partner Loan Support Missing",
            category="OWNER_PARTNER_TRANSACTIONS",
            severity="MEDIUM",
            status="PASSED",
            return_type=job.return_type,
            evidence_document=evidence_doc,
            evidence_text=evidence_text
        )
        
    severity = "HIGH" if max_amount > ANOMALY_RULE_CONFIG.get("owner_loan_materiality_threshold", 10000.0) else "MEDIUM"
    
    return make_anomaly_result(
        rule_id="OWN-001",
        rule_name="Shareholder / Partner Loan Support Missing",
        category="OWNER_PARTNER_TRANSACTIONS",
        severity=severity,
        status="FLAGGED",
        return_type=job.return_type,
        evidence_document=evidence_doc,
        evidence_text=evidence_text,
        extracted_amount=max_amount if max_amount > 0 else None,
        missing_support=["LOAN_STATEMENT", "SHAREHOLDER_DISTRIBUTION", "PARTNER_DISTRIBUTION", "OWNERSHIP_SCHEDULE"],
        recommended_action="Review owner/shareholder/partner loan activity and request loan agreement, repayment schedule, or owner transaction support.",
        review_required_by="TAX_PREPARER"
    )

def check_rule_OWN_002(job, doc_types, extracted_vals, files):
    if job.return_type not in ["1120-S", "1065"]:
        return make_anomaly_result(
            rule_id="OWN-002",
            rule_name="Distribution Exceeds Capital / Basis Warning",
            category="OWNER_PARTNER_TRANSACTIONS",
            severity="MEDIUM",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason="Rule only applies to 1120-S or 1065 returns."
        )
        
    dist_key = "shareholder_distributions" if job.return_type == "1120-S" else "partner_distributions"
    
    can_run, reason = check_rule_preconditions(
        required_values=["beginning_capital", "current_year_income", "capital_contributions", dist_key],
        extracted_values=extracted_vals
    )
    if not can_run:
        return make_anomaly_result(
            rule_id="OWN-002",
            rule_name="Distribution Exceeds Capital / Basis Warning",
            category="OWNER_PARTNER_TRANSACTIONS",
            severity="MEDIUM",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason=reason
        )
        
    beg_cap = extracted_vals["beginning_capital"]
    cy_inc = extracted_vals["current_year_income"]
    cap_contrib = extracted_vals["capital_contributions"]
    distributions = extracted_vals[dist_key]
    
    limit = beg_cap + cy_inc + cap_contrib
    difference = distributions - limit
    tolerance = ANOMALY_RULE_CONFIG.get("distribution_capital_tolerance", 5.00)
    
    exceeds = difference > tolerance
    status = "FLAGGED" if exceeds else "PASSED"
    
    evidence_text = f"Distributions (${distributions:,.2f}) exceed capital basis indicator (${limit:,.2f}) by ${difference:,.2f}."
    
    return make_anomaly_result(
        rule_id="OWN-002",
        rule_name="Distribution Exceeds Capital / Basis Warning",
        category="OWNER_PARTNER_TRANSACTIONS",
        severity="MEDIUM",
        status=status,
        return_type=job.return_type,
        evidence_text=evidence_text if exceeds else None,
        extracted_amount=distributions,
        expected_amount=limit,
        difference=difference if exceeds else None,
        tolerance=tolerance,
        recommended_action="Review whether distributions exceed available capital/basis indicators and verify K-1, capital account, and distribution support.",
        review_required_by="TAX_PREPARER"
    )

def check_rule_OWN_003(job, doc_types, extracted_vals, files):
    if job.return_type != "1120-S":
        return make_anomaly_result(
            rule_id="OWN-003",
            rule_name="Unequal S-Corp Distribution Warning",
            category="OWNER_PARTNER_TRANSACTIONS",
            severity="HIGH",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason="Rule only applies to 1120-S returns."
        )
        
    can_run, reason = check_rule_preconditions(
        required_documents=["OWNERSHIP_SCHEDULE", "SHAREHOLDER_DISTRIBUTION", "K1_WORKSHEET"],
        required_values=["shareholder_ownership_percentages", "shareholder_distribution_percentages"],
        uploaded_doc_types=doc_types,
        extracted_values=extracted_vals
    )
    if not can_run:
        return make_anomaly_result(
            rule_id="OWN-003",
            rule_name="Unequal S-Corp Distribution Warning",
            category="OWNER_PARTNER_TRANSACTIONS",
            severity="HIGH",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason=reason
        )
        
    ownerships = extracted_vals["shareholder_ownership_percentages"]
    distributions = extracted_vals["shareholder_distribution_percentages"]
    
    mismatches = []
    max_diff = 0.0
    extracted_val = None
    expected_val = None
    
    if isinstance(ownerships, dict) and isinstance(distributions, dict):
        for owner, pct in ownerships.items():
            dist_pct = distributions.get(owner)
            if dist_pct is not None:
                diff = abs(dist_pct - pct)
                if diff > ANOMALY_RULE_CONFIG.get("ownership_distribution_percent_tolerance", 0.01):
                    mismatches.append(f"Owner '{owner}' owns {pct*100:.2f}%, received {dist_pct*100:.2f}% of distributions (difference: {diff*100:.2f}%)")
                    if diff > max_diff:
                        max_diff = diff
                        extracted_val = dist_pct
                        expected_val = pct
    elif isinstance(ownerships, list) and isinstance(distributions, list) and len(ownerships) == len(distributions):
        for idx, (pct, dist_pct) in enumerate(zip(ownerships, distributions)):
            diff = abs(dist_pct - pct)
            if diff > ANOMALY_RULE_CONFIG.get("ownership_distribution_percent_tolerance", 0.01):
                mismatches.append(f"Owner {idx+1} owns {pct*100:.2f}%, received {dist_pct*100:.2f}% of distributions (difference: {diff*100:.2f}%)")
                if diff > max_diff:
                    max_diff = diff
                    extracted_val = dist_pct
                    expected_val = pct
                    
    if not mismatches:
        return make_anomaly_result(
            rule_id="OWN-003",
            rule_name="Unequal S-Corp Distribution Warning",
            category="OWNER_PARTNER_TRANSACTIONS",
            severity="HIGH",
            status="PASSED",
            return_type=job.return_type
        )
        
    evidence_text = "Unequal S-Corp distributions detected: " + "; ".join(mismatches)
    
    conf_score = None
    for f in files:
        if f.detected_document_type in ["OWNERSHIP_SCHEDULE", "K1_WORKSHEET", "SHAREHOLDER_DISTRIBUTION"]:
            conf_score = f.confidence_score
            break
            
    return make_anomaly_result(
        rule_id="OWN-003",
        rule_name="Unequal S-Corp Distribution Warning",
        category="OWNER_PARTNER_TRANSACTIONS",
        severity="HIGH",
        status="FLAGGED",
        confidence_score=conf_score,
        return_type=job.return_type,
        evidence_text=evidence_text,
        extracted_amount=extracted_val,
        expected_amount=expected_val,
        difference=max_diff,
        tolerance=ANOMALY_RULE_CONFIG.get("ownership_distribution_percent_tolerance", 0.01),
        recommended_action="Review S-Corp distribution allocation against ownership percentages and K-1 support.",
        review_required_by="TAX_PREPARER"
    )

def check_rule_OWN_004(job, doc_types, extracted_vals, files):
    if job.return_type != "1065":
        return make_anomaly_result(
            rule_id="OWN-004",
            rule_name="Partner Guaranteed Payments Support Missing",
            category="OWNER_PARTNER_TRANSACTIONS",
            severity="MEDIUM",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason="Rule only applies to 1065 returns."
        )
        
    trigger_keywords = [
        "guaranteed payment", "guaranteed payments", "partner payment",
        "partner salary", "partner compensation", "payment to partner"
    ]
    
    has_support = "K1_WORKSHEET" in doc_types and "CAPITAL_ACCOUNT_SCHEDULE" in doc_types and "OWNERSHIP_SCHEDULE" in doc_types
    
    triggered = False
    detected_amount = 0.0
    evidence_text = None
    evidence_doc = None
    
    for job_file in files:
        txt_path = os.path.join(os.getcwd(), job_file.file_path + ".txt")
        if not os.path.exists(txt_path):
            continue
        try:
            with open(txt_path, "r", encoding="utf-8") as f:
                file_text = f.read()
            for line in file_text.split("\n"):
                line_lower = line.lower()
                for kw in trigger_keywords:
                    if kw in line_lower:
                        triggered = True
                        val = extract_numeric_value(line)
                        if val is not None:
                            val_abs = abs(val)
                            if val_abs > detected_amount:
                                detected_amount = val_abs
                        if not evidence_text:
                            evidence_text = f"Found guaranteed payments keyword '{kw}' in {job_file.file_name}: '{line.strip()}'"
                            evidence_doc = job_file.file_name
        except Exception:
            pass
            
    if not triggered:
        return make_anomaly_result(
            rule_id="OWN-004",
            rule_name="Partner Guaranteed Payments Support Missing",
            category="OWNER_PARTNER_TRANSACTIONS",
            severity="MEDIUM",
            status="PASSED",
            return_type=job.return_type
        )
        
    if has_support:
        return make_anomaly_result(
            rule_id="OWN-004",
            rule_name="Partner Guaranteed Payments Support Missing",
            category="OWNER_PARTNER_TRANSACTIONS",
            severity="MEDIUM",
            status="PASSED",
            return_type=job.return_type,
            evidence_document=evidence_doc,
            evidence_text=evidence_text,
            extracted_amount=detected_amount if detected_amount > 0 else None
        )
        
    return make_anomaly_result(
        rule_id="OWN-004",
        rule_name="Partner Guaranteed Payments Support Missing",
        category="OWNER_PARTNER_TRANSACTIONS",
        severity="MEDIUM",
        status="FLAGGED",
        return_type=job.return_type,
        evidence_document=evidence_doc,
        evidence_text=evidence_text,
        extracted_amount=detected_amount if detected_amount > 0 else None,
        missing_support=[doc for doc in ["K1_WORKSHEET", "CAPITAL_ACCOUNT_SCHEDULE", "OWNERSHIP_SCHEDULE"] if doc not in doc_types],
        recommended_action="Review guaranteed payments and verify partner-level allocation, K-1 support, and capital account treatment.",
        review_required_by="TAX_PREPARER"
    )

def check_rule_PY_003(job, doc_types, extracted_vals, files):
    if job.return_type not in ["1120-S", "1065"]:
        return make_anomaly_result(
            rule_id="PY-003",
            rule_name="Partner / Shareholder Capital Mismatch",
            category="PRIOR_YEAR_ROLL_FORWARD",
            severity="HIGH",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason="Rule only applies to 1120-S or 1065 returns."
        )
        
    can_run, reason = check_rule_preconditions(
        required_documents=["PRIOR_YEAR_RETURN", "K1_WORKSHEET", "CAPITAL_ACCOUNT_SCHEDULE"],
        required_values=["prior_year_ending_capital", "current_year_beginning_capital"],
        uploaded_doc_types=doc_types,
        extracted_values=extracted_vals
    )
    if not can_run:
        return make_anomaly_result(
            rule_id="PY-003",
            rule_name="Partner / Shareholder Capital Mismatch",
            category="PRIOR_YEAR_ROLL_FORWARD",
            severity="HIGH",
            status="SKIPPED",
            return_type=job.return_type,
            skip_reason=reason
        )
        
    prior_year_ending_cap = extracted_vals["prior_year_ending_capital"]
    current_year_beg_cap = extracted_vals["current_year_beginning_capital"]
    
    tie_out = check_tie_out(current_year_beg_cap, prior_year_ending_cap, tolerance=5.00)
    status = "PASSED" if tie_out["passed"] else "FLAGGED"
    
    evidence_text = f"Current year beginning capital (${current_year_beg_cap:,.2f}) does not match prior year ending capital (${prior_year_ending_cap:,.2f}). Difference is ${tie_out['difference']:,.2f}."
    
    return make_anomaly_result(
        rule_id="PY-003",
        rule_name="Partner / Shareholder Capital Mismatch",
        category="PRIOR_YEAR_ROLL_FORWARD",
        severity="HIGH",
        status=status,
        return_type=job.return_type,
        evidence_text=evidence_text if not tie_out["passed"] else None,
        extracted_amount=current_year_beg_cap,
        expected_amount=prior_year_ending_cap,
        difference=tie_out["difference"],
        tolerance=tie_out["tolerance"],
        recommended_action="Review prior-year K-1 ending capital and current-year beginning capital account balances.",
        review_required_by="TAX_PREPARER"
    )

def run_anomaly_rules(job_id: int, db: Session) -> int:
    """
    Executes core missing-document, base rules, Phase 1 advanced anomaly checks, and Phase 2 entity rules.
    """
    print(f"[AnomalyEngine] Running rules for job ID: {job_id}")
    
    # 1. Retrieve job details and inventory
    job = db.query(TaxJob).filter(TaxJob.id == job_id).first()
    if not job:
        print(f"[AnomalyEngine] Error: Job ID {job_id} not found.")
        return 0
        
    # Harvest financial metrics first
    harvest_job_financial_metrics(job_id, db)
    extracted_vals = get_extracted_values(job_id, db)
    
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
    
    # Clear existing checklist items for safe reprocessing
    db.query(ChecklistItem).filter(ChecklistItem.tax_job_id == job_id).delete()
    db.commit()
    
    raw_results = []
    
    # Core missing document checks A-E
    raw_results.append(check_rule_A(job, doc_types, extracted_vals, files, all_text_lower))
    raw_results.append(check_rule_B(job, doc_types, extracted_vals, files, all_text_lower))
    raw_results.append(check_rule_C(job, doc_types, extracted_vals, files, all_text_lower))
    raw_results.append(check_rule_D(job, doc_types, extracted_vals, files, all_text_lower))
    raw_results.append(check_rule_E(job, doc_types, extracted_vals, files, all_text_lower))
    
    # Trigger-based checks F-K and M
    raw_results.append(check_rule_F(job, doc_types, extracted_vals, files, all_text_lower))
    raw_results.append(check_rule_G(job, doc_types, extracted_vals, files, all_text_lower))
    raw_results.append(check_rule_H(job, doc_types, extracted_vals, files, all_text_lower))
    raw_results.append(check_rule_I(job, doc_types, extracted_vals, files, all_text_lower))
    raw_results.append(check_rule_J(job, doc_types, extracted_vals, files, all_text_lower))
    raw_results.append(check_rule_K(job, doc_types, extracted_vals, files, all_text_lower))
    raw_results.append(check_rule_M(job, doc_types, extracted_vals, files, all_text_lower))
    
    # Math & other base checks L, N, BS-001
    raw_results.append(check_rule_L(job, doc_types, extracted_vals, files, all_text_lower))
    raw_results.append(check_rule_N(job, doc_types, extracted_vals, files, all_text_lower))
    
    bs_res = check_rule_BS_001(job, doc_types, extracted_vals, files, db)
    if isinstance(bs_res, list):
        raw_results.extend(bs_res)
    else:
        raw_results.append(bs_res)
        
    # Phase 1 Advanced Rules
    raw_results.append(check_rule_PY_001(job, doc_types, extracted_vals, files, db))
    raw_results.append(check_rule_PY_002(job, doc_types, extracted_vals, files))
    raw_results.append(check_rule_BST_001(job, doc_types, extracted_vals, files, db))
    raw_results.append(check_rule_BST_002(job, doc_types, extracted_vals, files, db))
    raw_results.append(check_rule_BST_003(job, doc_types, extracted_vals, files, db))
    raw_results.append(check_rule_REV_001(job, doc_types, extracted_vals, files, db))
    raw_results.append(check_rule_REV_002(job, doc_types, extracted_vals, files, db))
    raw_results.append(check_rule_PAY_002(job, doc_types, extracted_vals, files, db))
    raw_results.append(check_rule_RT_001(job, doc_types, extracted_vals, files, all_text_lower))
    raw_results.append(check_rule_OCR_004(job, doc_types, extracted_vals, files))
    raw_results.append(check_rule_OCR_005(job, doc_types, extracted_vals, files))
    
    # Phase 2 Entity Specific Rules
    raw_results.append(check_rule_OWN_001(job, doc_types, extracted_vals, files))
    raw_results.append(check_rule_OWN_002(job, doc_types, extracted_vals, files))
    raw_results.append(check_rule_OWN_003(job, doc_types, extracted_vals, files))
    raw_results.append(check_rule_OWN_004(job, doc_types, extracted_vals, files))
    raw_results.append(check_rule_PY_003(job, doc_types, extracted_vals, files))
    
    # Filter and convert FLAGGED results to ChecklistItems
    findings = []
    for r in raw_results:
        if r is None:
            continue
        if r.get("status") == "FLAGGED":
            findings.append(map_anomaly_result_to_checklist_item(job.id, r))
            
    for item in findings:
        db.add(item)
    db.commit()
    
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
