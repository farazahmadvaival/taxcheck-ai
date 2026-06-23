import pytest
from unittest.mock import MagicMock
from app.services.anomaly_engine import check_rule_PAY_002, make_anomaly_result

def test_existing_rule_returns_standard_output_format():
    # Setup mock job
    job = MagicMock()
    job.id = 1
    job.return_type = "1120-S"
    
    doc_types = {"PAYROLL_SUMMARY", "BALANCE_SHEET", "INCOME_STATEMENT"}
    extracted_vals = {
        "gross_receipts": 100000.0
    }
    
    # Mock database session
    db = MagicMock()
    
    # Mock JobFile records
    mock_payroll_file = MagicMock()
    mock_payroll_file.file_name = "payroll_summary.txt"
    mock_payroll_file.file_path = "mock_path_payroll"
    mock_payroll_file.detected_document_type = "PAYROLL_SUMMARY"
    
    db.query().filter().all.return_value = [mock_payroll_file]
    
    # Call rule using patched file checks
    import builtins
    original_open = builtins.open
    
    def mock_open(file, *args, **kwargs):
        if "mock_path_payroll" in str(file):
            m = MagicMock()
            m.__enter__.return_value.read.return_value = "W-3 Total Wages: 184500.00"
            return m
        elif "mock_path" in str(file):
            m = MagicMock()
            m.__enter__.return_value.read.return_value = "Wages and Salaries: 184500.00"
            return m
        return original_open(file, *args, **kwargs)
        
    import os
    original_exists = os.path.exists
    def mock_exists(path):
        if "mock_path" in str(path):
            return True
        return original_exists(path)
        
    import unittest.mock as mock
    with mock.patch("builtins.open", mock_open), mock.patch("os.path.exists", mock_exists):
        result = check_rule_PAY_002(job, doc_types, extracted_vals, [], db)
        
    # Assert result structure keys
    expected_keys = {
        "rule_id", "rule_name", "category", "severity", "status", "confidence_score",
        "return_type", "evidence_document", "evidence_text", "extracted_amount",
        "expected_amount", "difference", "tolerance", "missing_support",
        "recommended_action", "review_required_by", "skip_reason"
    }
    assert set(result.keys()) == expected_keys
