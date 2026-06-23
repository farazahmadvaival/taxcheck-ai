from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class JobFile(Base):
    __tablename__ = "job_files"

    id = Column(Integer, primary_key=True, index=True)
    tax_job_id = Column(Integer, ForeignKey("tax_jobs.id"), nullable=False)
    upload_round_id = Column(Integer, ForeignKey("upload_rounds.id"), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False) # e.g. pdf, xlsx, png, zip
    detected_document_type = Column(String(100), nullable=True) # e.g. TRIAL_BALANCE, BALANCE_SHEET, etc.
    page_count = Column(Integer, nullable=True)
    extraction_method = Column(String(100), nullable=True) # e.g. pdfplumber, openpyxl, paddleocr, gemini-flash
    confidence_score = Column(Float, nullable=True)
    is_processed = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    tax_job = relationship("TaxJob", back_populates="files")
    upload_round = relationship("UploadRound", back_populates="files")
