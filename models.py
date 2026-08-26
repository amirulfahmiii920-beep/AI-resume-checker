from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100))
    email = Column(String(100), unique=True, index=True)
    ai_quota = Column(Integer, default=3)

    evaluations = relationship("ResumeEvaluation", back_populates="user")

class ResumeEvaluation(Base):
    __tablename__ = "resume_evaluations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    file_name = Column(String(255))
    original_text = Column(Text)
    ats_score = Column(Float)
    strengths = Column(Text)
    weaknesses = Column(Text)
    user = relationship("User", back_populates="evaluations")