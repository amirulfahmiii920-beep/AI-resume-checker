from sqlalchemy import Column, Integer, String, Float, Text
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class ResumeEvaluation(Base):
    __tablename__ = "resume_evaluations"

    id = Column(Integer, primary_key=True, index=True)
    file_name = Column(String(255))
    original_text = Column(Text)
    ats_score = Column(Float)
    strengths = Column(Text)
    weaknesses = Column(Text)