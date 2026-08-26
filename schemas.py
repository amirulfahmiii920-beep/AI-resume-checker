from pydantic import BaseModel
from typing import Optional

# Schema for creating a new user from frontend
class UserCreate(BaseModel):
    name: str
    email: str

# Schema for sending User data back to frontend
class UserResponse(BaseModel):
    id: int
    name: str
    email: str

    class Config:
        from_attributes = True

# Schema for saving a new Resume Evaluation
class ResumeEvaluationCreate(BaseModel):
    file_name: str
    ats_score: float
    strengths: str
    weaknesses: str

# Schema for sending Resume Evaluation data back to frontend
class ResumeEvaluationResponse(BaseModel):
    id: int
    file_name: str
    ats_score: float
    strengths: str
    weaknesses: str

    class Config:
        from_attributes = True