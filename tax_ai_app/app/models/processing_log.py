from datetime import datetime
import re
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.database import Base

def mask_sensitive_data(text: str) -> str:
    if not text:
        return text

    # Ensure no full document text is stored in the database logs by truncating large chunks
    if len(text) > 4000:
        text = text[:4000] + "\n... [TRUNCATED FOR SECURITY/COMPLIANCE]"

    # Mask SSN: e.g. 000-00-0000 or 000 00 0000
    ssn_pattern = re.compile(r'\b\d{3}[- ]\d{2}[- ]\d{4}\b')
    text = ssn_pattern.sub("[SSN_MASKED]", text)
    
    # Mask EIN: e.g. 00-0000000 or 00 0000000
    ein_pattern = re.compile(r'\b\d{2}[- ]\d{7}\b')
    text = ein_pattern.sub("[EIN_MASKED]", text)
    
    # Mask Bank Account numbers: 8 to 17 consecutive digits
    bank_pattern = re.compile(r'\b\d{8,17}\b')
    text = bank_pattern.sub("[ACCOUNT_MASKED]", text)
    
    return text

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

    def __init__(self, **kwargs):
        if "message" in kwargs:
            kwargs["message"] = mask_sensitive_data(kwargs["message"])
        super().__init__(**kwargs)

    # Relationships
    tax_job = relationship("TaxJob", back_populates="logs")

