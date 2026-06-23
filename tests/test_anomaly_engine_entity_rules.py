import pytest
from unittest.mock import MagicMock, patch
import os
from app.services.anomaly_engine import (
    check_rule_OWN_001,
    check_rule_OWN_002,
    check_rule_OWN_003,
    check_rule_OWN_004,
    check_rule_PY_003
)

def test_OWN_001_flags_when_keyword_exists_and_support_missing():
    job = MagicMock()
    job.return_type = "1120-S"
    doc_types = set() # No support
    extracted_vals = {}
    
    # Mock a file with a keyword
    mock_file = MagicMock()
    mock_file.file_name = "ledger.txt"
    mock_file.file_path = "mock_ledger"
    
    def mock_open(file, *args, **kwargs):
        m = MagicMock()
        m.__enter__.return_value.read.return_value = "Loan from shareholder: 15000.00"
        return m
        
    def mock_exists(path):
        return True
        
    with patch("builtins.open", mock_open), patch("os.path.exists", mock_exists):
        result = check_rule_OWN_001(job, doc_types, extracted_vals, [mock_file])
        
    assert result["status"] == "FLAGGED"
    assert result["severity"] == "HIGH"  # Exceeds 10000.00
    assert result["extracted_amount"] == 15000.00
    assert "Loan from shareholder" in result["evidence_text"]

def test_OWN_001_does_not_flag_when_support_exists():
    job = MagicMock()
    job.return_type = "1120-S"
    doc_types = {"LOAN_STATEMENT"} # Support exists
    extracted_vals = {}
    
    mock_file = MagicMock()
    mock_file.file_name = "ledger.txt"
    mock_file.file_path = "mock_ledger"
    
    def mock_open(file, *args, **kwargs):
        m = MagicMock()
        m.__enter__.return_value.read.return_value = "Loan from shareholder: 15000.00"
        return m
        
    with patch("builtins.open", mock_open), patch("os.path.exists", lambda p: True):
        result = check_rule_OWN_001(job, doc_types, extracted_vals, [mock_file])
        
    assert result["status"] == "PASSED"

def test_OWN_002_flags_when_distributions_exceed_capital():
    job = MagicMock()
    job.return_type = "1120-S"
    doc_types = set()
    extracted_vals = {
        "beginning_capital": 5000.0,
        "current_year_income": 3000.0,
        "capital_contributions": 1000.0,
        "shareholder_distributions": 12000.0 # Exceeds limit (9000.0)
    }
    
    result = check_rule_OWN_002(job, doc_types, extracted_vals, [])
    assert result["status"] == "FLAGGED"
    assert result["difference"] == 3000.0

def test_OWN_002_returns_skipped_when_capital_values_missing():
    job = MagicMock()
    job.return_type = "1120-S"
    doc_types = set()
    extracted_vals = {
        "beginning_capital": 5000.0,
        "shareholder_distributions": 12000.0
        # missing current_year_income, capital_contributions
    }
    
    result = check_rule_OWN_002(job, doc_types, extracted_vals, [])
    assert result["status"] == "SKIPPED"
    assert "Missing required extracted value(s)" in result["skip_reason"]

def test_OWN_003_flags_unequal_scorp_distributions():
    job = MagicMock()
    job.return_type = "1120-S"
    doc_types = {"OWNERSHIP_SCHEDULE", "SHAREHOLDER_DISTRIBUTION", "K1_WORKSHEET"}
    extracted_vals = {
        "shareholder_ownership_percentages": [0.50, 0.50],
        "shareholder_distribution_percentages": [0.80, 0.20] # 80% vs 20%
    }
    
    result = check_rule_OWN_003(job, doc_types, extracted_vals, [])
    assert result["status"] == "FLAGGED"
    assert "Unequal S-Corp distributions detected" in result["evidence_text"]
    assert pytest.approx(result["difference"]) == 0.30
    assert pytest.approx(result["extracted_amount"]) == 0.80
    assert pytest.approx(result["expected_amount"]) == 0.50
    assert pytest.approx(result["tolerance"]) == 0.01

def test_OWN_003_returns_skipped_when_ownership_schedule_missing():
    job = MagicMock()
    job.return_type = "1120-S"
    doc_types = {"SHAREHOLDER_DISTRIBUTION", "K1_WORKSHEET"} # Missing OWNERSHIP_SCHEDULE
    extracted_vals = {
        "shareholder_ownership_percentages": [0.50, 0.50],
        "shareholder_distribution_percentages": [0.80, 0.20]
    }
    
    result = check_rule_OWN_003(job, doc_types, extracted_vals, [])
    assert result["status"] == "SKIPPED"
    assert "Missing required document(s)" in result["skip_reason"]

def test_OWN_004_flags_guaranteed_payments_without_support():
    job = MagicMock()
    job.return_type = "1065"
    doc_types = set() # Missing support
    extracted_vals = {}
    
    mock_file = MagicMock()
    mock_file.file_name = "k1.txt"
    mock_file.file_path = "mock_k1"
    
    def mock_open(file, *args, **kwargs):
        m = MagicMock()
        m.__enter__.return_value.read.return_value = "Guaranteed payment to partner: 8000.00"
        return m
        
    with patch("builtins.open", mock_open), patch("os.path.exists", lambda p: True):
        result = check_rule_OWN_004(job, doc_types, extracted_vals, [mock_file])
        
    assert result["status"] == "FLAGGED"
    assert result["extracted_amount"] == 8000.00

def test_PY_003_flags_prior_year_ending_capital_mismatch():
    job = MagicMock()
    job.return_type = "1065"
    doc_types = {"PRIOR_YEAR_RETURN", "K1_WORKSHEET", "CAPITAL_ACCOUNT_SCHEDULE"}
    extracted_vals = {
        "prior_year_ending_capital": 5000.00,
        "current_year_beginning_capital": 5500.00 # Mismatch > $5.00
    }
    
    result = check_rule_PY_003(job, doc_types, extracted_vals, [])
    assert result["status"] == "FLAGGED"
    assert result["difference"] == 500.00

def test_PY_003_passes_within_tolerance():
    job = MagicMock()
    job.return_type = "1065"
    doc_types = {"PRIOR_YEAR_RETURN", "K1_WORKSHEET", "CAPITAL_ACCOUNT_SCHEDULE"}
    extracted_vals = {
        "prior_year_ending_capital": 5000.00,
        "current_year_beginning_capital": 5003.00 # Difference of 3.0 is within 5.0 tolerance
    }
    
    result = check_rule_PY_003(job, doc_types, extracted_vals, [])
    assert result["status"] == "PASSED"
