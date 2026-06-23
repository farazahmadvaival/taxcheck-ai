from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class UploadRound(Base):
    __tablename__ = "upload_rounds"

    TYPE_INITIAL = "INITIAL"
    TYPE_MISSING_DOCUMENTS = "MISSING_DOCUMENTS"

    id = Column(Integer, primary_key=True, index=True)
    tax_job_id = Column(Integer, ForeignKey("tax_jobs.id"), nullable=False)
    round_number = Column(Integer, nullable=False, default=1)
    upload_type = Column(String(50), nullable=False, default=TYPE_INITIAL) # INITIAL / MISSING_DOCUMENTS
    zip_path = Column(String(255), nullable=True)
    status = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    tax_job = relationship("TaxJob", back_populates="upload_rounds")
    files = relationship("JobFile", back_populates="upload_round", cascade="all, delete-orphan")
