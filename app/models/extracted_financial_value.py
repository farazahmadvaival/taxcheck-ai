from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Float, Numeric
from sqlalchemy.orm import relationship
from app.database import Base

class ExtractedFinancialValue(Base):
    __tablename__ = "extracted_financial_values"

    id = Column(Integer, primary_key=True, index=True)
    tax_job_id = Column(Integer, ForeignKey("tax_jobs.id"), nullable=False)
    job_file_id = Column(Integer, ForeignKey("job_files.id"), nullable=True)
    value_key = Column(String(100), nullable=False)  # e.g., "total_assets_ending"
    value_label = Column(Text, nullable=True)        # Raw label matched in document (e.g., "Total Assets:")
    amount = Column(Numeric(14, 2), nullable=True)
    period_type = Column(String(50), nullable=True)   # "BEGINNING", "ENDING", etc.
    source_page = Column(Integer, nullable=True)
    source_text = Column(Text, nullable=True)
    confidence_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    tax_job = relationship("TaxJob")
    job_file = relationship("JobFile")
