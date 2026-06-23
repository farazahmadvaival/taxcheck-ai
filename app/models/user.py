from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="preparer")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    jobs_created = relationship("TaxJob", back_populates="creator")
    emails_approved = relationship("EmailRequest", back_populates="approver")
