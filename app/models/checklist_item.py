from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.database import Base

class ChecklistItem(Base):
    __tablename__ = "checklist_items"

    # Type Constants
    TYPE_MISSING_DOCUMENT = "MISSING_DOCUMENT"
    TYPE_ANOMALY = "ANOMALY"
    TYPE_WARNING = "WARNING"

    # Severity Constants
    SEVERITY_HIGH = "HIGH"
    SEVERITY_MEDIUM = "MEDIUM"
    SEVERITY_LOW = "LOW"

    # Status Constants
    STATUS_OPEN = "OPEN"
    STATUS_APPROVED = "APPROVED"
    STATUS_IGNORED = "IGNORED"
    STATUS_RESOLVED = "RESOLVED"

    id = Column(Integer, primary_key=True, index=True)
    tax_job_id = Column(Integer, ForeignKey("tax_jobs.id"), nullable=False)
    type = Column(String(50), nullable=False, default=TYPE_MISSING_DOCUMENT) # MISSING_DOCUMENT / ANOMALY / WARNING
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(String(50), nullable=False, default=SEVERITY_MEDIUM) # HIGH / MEDIUM / LOW
    status = Column(String(50), nullable=False, default=STATUS_OPEN) # OPEN / APPROVED / IGNORED / RESOLVED
    source_file = Column(String(255), nullable=True)
    source_page = Column(Integer, nullable=True)
    recommended_document = Column(String(255), nullable=True)
    email_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    tax_job = relationship("TaxJob", back_populates="checklist_items")
