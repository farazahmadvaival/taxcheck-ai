from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.database import Base

class ProcessingLog(Base):
    __tablename__ = "processing_logs"

    LEVEL_INFO = "INFO"
    LEVEL_WARNING = "WARNING"
    LEVEL_ERROR = "ERROR"

    id = Column(Integer, primary_key=True, index=True)
    tax_job_id = Column(Integer, ForeignKey("tax_jobs.id"), nullable=False)
    level = Column(String(50), nullable=False, default=LEVEL_INFO) # INFO / WARNING / ERROR
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    tax_job = relationship("TaxJob", back_populates="logs")
