import pytest
from app.services.anomaly_engine import check_rule_preconditions, check_rule_PY_002
from unittest.mock import MagicMock

def test_precondition_helper_behavior():
    # Test doc missing
    can_run, reason = check_rule_preconditions(
        required_documents=["BALANCE_SHEET"],
        uploaded_doc_types=[]
    )
    assert not can_run
    assert "Missing required document(s)" in reason
    
    # Test values missing
    can_run, reason = check_rule_preconditions(
        required_values=["net_income"],
        extracted_values={}
    )
    assert not can_run
    assert "Missing required extracted value(s)" in reason
    
    # Test success
    can_run, reason = check_rule_preconditions(
        required_documents=["BALANCE_SHEET"],
        required_values=["net_income"],
        uploaded_doc_types=["BALANCE_SHEET"],
        extracted_values={"net_income": 50000.0}
    )
    assert can_run
    assert reason is None

def test_rule_skipped_when_preconditions_fail():
    job = MagicMock()
    job.return_type = "1120-S"
    
    # Missing required extracted value: retained_earnings_beginning
    extracted_vals = {
        "retained_earnings_ending": 10000.0,
        "net_income": 5000.0
    }
    
    result = check_rule_PY_002(job, set(), extracted_vals, [])
    assert result["status"] == "SKIPPED"
    assert "Missing required extracted value(s)" in result["skip_reason"]
