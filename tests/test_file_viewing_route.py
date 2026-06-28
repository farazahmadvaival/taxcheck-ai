import pytest
from unittest.mock import MagicMock, patch
import os
from fastapi import HTTPException
from app.routes.jobs import view_file_by_name

@patch("app.routes.jobs.get_current_user_from_cookie")
@patch("os.path.exists")
@patch("app.routes.jobs.FileResponse")
def test_view_file_by_name_success(mock_file_response, mock_exists, mock_get_user):
    # Setup mocks
    mock_user = MagicMock()
    mock_get_user.return_value = mock_user
    mock_exists.return_value = True
    
    mock_request = MagicMock()
    
    # Mock database session
    mock_db = MagicMock()
    mock_job_file = MagicMock()
    mock_job_file.tax_job_id = 1
    mock_job_file.file_name = "test_doc.pdf"
    mock_job_file.file_path = "storage/jobs/1/extracted/round_1/test_doc.pdf"
    mock_job_file.file_type = "pdf"
    
    # db.query(JobFile).filter().first() returns mock_job_file
    mock_db.query().filter().first.return_value = mock_job_file
    
    # Mock FileResponse instance
    expected_response = MagicMock()
    mock_file_response.return_value = expected_response
    
    # Call endpoint
    res = view_file_by_name(id=1, filename="test_doc.pdf", request=mock_request, db=mock_db)
    
    # Assertions
    assert res == expected_response
    mock_file_response.assert_called_once()
    
    # Verify FileResponse arguments
    called_path = mock_file_response.call_args[0][0]
    called_kwargs = mock_file_response.call_args[1]
    
    assert called_path.endswith("storage/jobs/1/extracted/round_1/test_doc.pdf")
    assert called_kwargs["filename"] == "test_doc.pdf"
    assert called_kwargs["media_type"] == "application/pdf"
    assert called_kwargs["content_disposition_type"] == "inline"

@patch("app.routes.jobs.get_current_user_from_cookie")
@patch("app.routes.jobs.RedirectResponse")
def test_view_file_by_name_not_found(mock_redirect_response, mock_get_user):
    mock_user = MagicMock()
    mock_get_user.return_value = mock_user
    
    mock_request = MagicMock()
    mock_db = MagicMock()
    # db.query(JobFile).filter().first() returns None
    mock_db.query().filter().first.return_value = None
    
    expected_redirect = MagicMock()
    mock_redirect_response.return_value = expected_redirect
    
    res = view_file_by_name(id=1, filename="nonexistent.pdf", request=mock_request, db=mock_db)
    
    assert res == expected_redirect
    mock_redirect_response.assert_called_once_with(
        url="/jobs/1?error=File+not+found:+nonexistent.pdf",
        status_code=303
    )
