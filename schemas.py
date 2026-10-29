from pydantic import BaseModel

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