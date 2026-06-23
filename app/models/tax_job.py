from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class TaxJob(Base):
    __tablename__ = "tax_jobs"

    # Status Constants (Section 6)
    STATUS_UPLOADED = "UPLOADED"
    STATUS_QUEUED = "QUEUED"
    STATUS_PROCESSING = "PROCESSING"
    STATUS_REVIEW_NEEDED = "REVIEW_NEEDED"
    STATUS_EMAIL_DRAFTED = "EMAIL_DRAFTED"
    STATUS_EMAIL_SENT = "EMAIL_SENT"
    STATUS_WAITING_CLIENT_DOCUMENTS = "WAITING_CLIENT_DOCUMENTS"
    STATUS_REPROCESSING = "REPROCESSING"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_FAILED = "FAILED"

    id = Column(Integer, primary_key=True, index=True)
    client_name = Column(String(100), nullable=False)
    client_email = Column(String(150), nullable=False)
    tax_year = Column(Integer, nullable=False)
    return_type = Column(String(50), nullable=False) # e.g. 1120-S, 1065, 1040
    status = Column(String(50), nullable=False, default=STATUS_UPLOADED)
    uploaded_zip_path = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    creator = relationship("User", back_populates="jobs_created")
    upload_rounds = relationship("UploadRound", back_populates="tax_job", cascade="all, delete-orphan")
    files = relationship("JobFile", back_populates="tax_job", cascade="all, delete-orphan")
    checklist_items = relationship("ChecklistItem", back_populates="tax_job", cascade="all, delete-orphan")
    emails = relationship("EmailRequest", back_populates="tax_job", cascade="all, delete-orphan")
    logs = relationship("ProcessingLog", back_populates="tax_job", cascade="all, delete-orphan")
