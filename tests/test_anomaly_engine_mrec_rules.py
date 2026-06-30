import pytest
from unittest.mock import MagicMock
from app.services.anomaly_engine import (
    check_rule_MREC_001,
    check_rule_MREC_002,
    check_rule_MREC_003,
    check_rule_MREC_004
)

def test_MREC_001_flags_when_reconciliation_required_but_missing_m1_m3():
    job = MagicMock()
    job.return_type = "1120-S"
    doc_types = set()
    extracted_vals = {
        "net_income": 10000.00,
        "taxable_income": 8000.00  # Material difference of 2000.00
    }
    files = [MagicMock(file_name="ledger.txt")]
    all_text_lower = "some ordinary general ledger text content with no schedule"
    
    result = check_rule_MREC_001(job, doc_types, extracted_vals, files, all_text_lower)
    assert result["status"] == "FLAGGED"
    assert result["difference"] == 2000.00
    assert "no Schedule M-1 or M-3" in result["evidence_text"]

def test_MREC_001_passes_when_reconciliation_present():
    job = MagicMock()
    job.return_type = "1120-S"
    doc_types = set()
    extracted_vals = {
        "net_income": 10000.00,
        "taxable_income": 8000.00
    }
    files = [MagicMock(file_name="ledger.txt")]
    all_text_lower = "schedule m-1 book-tax reconciliation details here..."
    
    result = check_rule_MREC_001(job, doc_types, extracted_vals, files, all_text_lower)
    assert result["status"] == "PASSED"

def test_MREC_001_skips_when_required_value_missing():
    job = MagicMock()
    job.return_type = "1120-S"
    doc_types = set()
    extracted_vals = {
        "taxable_income": 8000.00  # Missing net_income
    }
    files = [MagicMock(file_name="ledger.txt")]
    all_text_lower = "some text"
    
    result = check_rule_MREC_001(job, doc_types, extracted_vals, files, all_text_lower)
    assert result["status"] == "SKIPPED"
    assert "Missing required extracted value(s)" in result["skip_reason"]

def test_MREC_001_skips_when_return_type_not_matching():
    job = MagicMock()
    job.return_type = "1040 / Schedule C"
    doc_types = set()
    extracted_vals = {
        "net_income": 10000.00,
        "taxable_income": 8000.00
    }
    files = []
    all_text_lower = "some text"
    
    result = check_rule_MREC_001(job, doc_types, extracted_vals, files, all_text_lower)
    assert result["status"] == "SKIPPED"
    assert "Rule only applies" in result["skip_reason"]

def test_MREC_002_flags_when_income_differs_without_reconciling_items():
    job = MagicMock()
    job.return_type = "1120"
    doc_types = set()
    extracted_vals = {
        "net_income": 12000.00,
        "taxable_income": 10000.00
    }
    files = []
    all_text_lower = "ordinary document without any reconcile keyword"
    
    result = check_rule_MREC_002(job, doc_types, extracted_vals, files, all_text_lower)
    assert result["status"] == "FLAGGED"
    assert result["difference"] == 2000.00
    assert "no reconciling items or adjustments" in result["evidence_text"]

def test_MREC_002_passes_when_reconciling_items_found():
    job = MagicMock()
    job.return_type = "1120"
    doc_types = set()
    extracted_vals = {
        "net_income": 12000.00,
        "taxable_income": 10000.00
    }
    files = []
    all_text_lower = "this is a temporary difference in depreciation adjustment"
    
    result = check_rule_MREC_002(job, doc_types, extracted_vals, files, all_text_lower)
    assert result["status"] == "PASSED"

def test_MREC_002_skips_when_required_value_missing():
    job = MagicMock()
    job.return_type = "1120"
    doc_types = set()
    extracted_vals = {
        "net_income": 12000.00  # Missing taxable_income
    }
    files = []
    all_text_lower = "some text"
    
    result = check_rule_MREC_002(job, doc_types, extracted_vals, files, all_text_lower)
    assert result["status"] == "SKIPPED"

def test_MREC_003_flags_when_non_deductible_keywords_lack_adjustments():
    job = MagicMock()
    job.return_type = "1120-S"
    doc_types = set()
    extracted_vals = {}
    files = []
    all_text_lower = "client paid penalties for late filing"
    
    result = check_rule_MREC_003(job, doc_types, extracted_vals, files, all_text_lower)
    assert result["status"] == "FLAGGED"
    assert "Non-deductible expense keywords detected: penalties" in result["evidence_text"]

def test_MREC_003_passes_when_adjustment_keywords_are_present():
    job = MagicMock()
    job.return_type = "1120-S"
    doc_types = set()
    extracted_vals = {}
    files = []
    all_text_lower = "client had meals expense, which is adjusted in meals limit and nondeductible meals"
    
    result = check_rule_MREC_003(job, doc_types, extracted_vals, files, all_text_lower)
    assert result["status"] == "PASSED"

def test_MREC_003_skips_when_no_keywords_present():
    job = MagicMock()
    job.return_type = "1120-S"
    doc_types = set()
    extracted_vals = {}
    files = []
    all_text_lower = "this is an ordinary text about software consulting services"
    
    result = check_rule_MREC_003(job, doc_types, extracted_vals, files, all_text_lower)
    assert result["status"] == "SKIPPED"
    assert "No non-deductible expense keywords" in result["skip_reason"]

def test_MREC_004_flags_retained_earnings_rollforward_mismatch_1120():
    job = MagicMock()
    job.return_type = "1120"
    doc_types = set()
    extracted_vals = {
        "retained_earnings_beginning": 10000.00,
        "retained_earnings_ending": 15000.00,
        "net_income": 6000.00,
        "dividends": 0.00
    }
    # Expected: 10000 + 6000 - 0 = 16000 != 15000
    
    result = check_rule_MREC_004(job, doc_types, extracted_vals, [])
    assert result["status"] == "FLAGGED"
    assert result["difference"] == 1000.00

def test_MREC_004_passes_retained_earnings_rollforward_1120():
    job = MagicMock()
    job.return_type = "1120"
    doc_types = set()
    extracted_vals = {
        "retained_earnings_beginning": 10000.00,
        "retained_earnings_ending": 16000.00,
        "net_income": 6000.00,
        "dividends": 0.00
    }
    
    result = check_rule_MREC_004(job, doc_types, extracted_vals, [])
    assert result["status"] == "PASSED"

def test_MREC_004_flags_aaa_rollforward_mismatch_1120s():
    job = MagicMock()
    job.return_type = "1120-S"
    doc_types = set()
    extracted_vals = {
        "beginning_aaa": 1000.00,
        "ending_aaa": 3000.00,
        "ordinary_business_income": 1500.00,
        "shareholder_distributions": 500.00,
        "nondeductible_expenses": 100.00
    }
    # Expected: 1000 + 1500 - 500 - 100 = 1900 != 3000
    
    result = check_rule_MREC_004(job, doc_types, extracted_vals, [])
    assert result["status"] == "FLAGGED"
    assert result["difference"] == 1100.00

def test_MREC_004_passes_aaa_rollforward_1120s():
    job = MagicMock()
    job.return_type = "1120-S"
    doc_types = set()
    extracted_vals = {
        "beginning_aaa": 1000.00,
        "ending_aaa": 1900.00,
        "ordinary_business_income": 1500.00,
        "shareholder_distributions": 500.00,
        "nondeductible_expenses": 100.00
    }
    
    result = check_rule_MREC_004(job, doc_types, extracted_vals, [])
    assert result["status"] == "PASSED"

def test_MREC_004_flags_capital_rollforward_mismatch_1065():
    job = MagicMock()
    job.return_type = "1065"
    doc_types = set()
    extracted_vals = {
        "beginning_capital": 5000.00,
        "ending_capital": 6500.00,
        "capital_contributions": 1000.00,
        "partner_distributions": 500.00,
        "net_income": 2000.00
    }
    # Expected: 5000 + 1000 + 2000 - 500 = 7500 != 6500
    
    result = check_rule_MREC_004(job, doc_types, extracted_vals, [])
    assert result["status"] == "FLAGGED"
    assert result["difference"] == 1000.00

def test_MREC_004_passes_capital_rollforward_1065():
    job = MagicMock()
    job.return_type = "1065"
    doc_types = set()
    extracted_vals = {
        "beginning_capital": 5000.00,
        "ending_capital": 7500.00,
        "capital_contributions": 1000.00,
        "partner_distributions": 500.00,
        "net_income": 2000.00
    }
    
    result = check_rule_MREC_004(job, doc_types, extracted_vals, [])
    assert result["status"] == "PASSED"

def test_MREC_004_skips_when_required_value_missing():
    job = MagicMock()
    job.return_type = "1065"
    doc_types = set()
    extracted_vals = {
        "beginning_capital": 5000.00,
        "capital_contributions": 1000.00,
        "partner_distributions": 500.00,
        "net_income": 2000.00
        # missing ending_capital
    }
    
    result = check_rule_MREC_004(job, doc_types, extracted_vals, [])
    assert result["status"] == "SKIPPED"
    assert "Missing required extracted value(s)" in result["skip_reason"]
