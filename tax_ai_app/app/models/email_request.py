from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.database import Base

class EmailRequest(Base):
    __tablename__ = "email_requests"

    STATUS_DRAFT = "DRAFT"
    STATUS_APPROVED = "APPROVED"
    STATUS_SENT = "SENT"
    STATUS_FAILED = "FAILED"

    id = Column(Integer, primary_key=True, index=True)
    tax_job_id = Column(Integer, ForeignKey("tax_jobs.id"), nullable=False)
    email_to = Column(String(255), nullable=False)
    subject = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    status = Column(String(50), nullable=False, default=STATUS_DRAFT) # DRAFT / APPROVED / SENT / FAILED
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    tax_job = relationship("TaxJob", back_populates="emails")
    approver = relationship("User", back_populates="emails_approved")
