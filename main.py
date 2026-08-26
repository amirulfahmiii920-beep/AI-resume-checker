import io
import os
import json
from typing import List  
from fastapi import FastAPI, Depends, HTTPException, File, UploadFile, Form
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from PyPDF2 import PdfReader
from dotenv import load_dotenv
from fastapi.responses import Response
from pydantic import BaseModel
import google.generativeai as genai
import pymysql
import models
import schemas
import pdfkit
import platform

class HTMLInput(BaseModel):
    html_content: str
# 1. Load environment variables securely
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 2. Configure Gemini AI
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("WARNING: GEMINI_API_KEY not found in .env file.")

# Initialize the Gemini model
ai_model = genai.GenerativeModel("gemini-3.5-flash")

# Initialize the Co-pilot model for rewriting
copilot_model = genai.GenerativeModel("gemini-3.6-flash")

# 3. Database setup
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(
    DATABASE_URL,
    connect_args={"ssl": {"check_hostname": False, "cert_reqs": 0}}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 4. User Registration API (POST)
@app.post("/users/", response_model=schemas.UserResponse)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(models.User).filter(models.User.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = models.User(name=user.name, email=user.email)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

# 5. The Core Feature: Upload & Analyze Resume (POST)
@app.post("/upload-resume/")
async def upload_resume(
    user_id: int = Form(...), 
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    # 1. Fetch user data from the database
    user_data = db.query(models.User).filter(models.User.id == user_id).first()
    
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
        
    # 2. Block the request if the quota is exhausted
    if user_data.ai_quota <= 0:
        raise HTTPException(status_code=429, detail="Your AI trial quota has been exhausted.")
    
    content = await file.read()
    
    try:
        pdf_file = io.BytesIO(content)
        pdf_reader = PdfReader(pdf_file)
        extracted_text = "".join([page.extract_text() for page in pdf_reader.pages])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading PDF: {str(e)}")
    
    try:
        # Generate prompt for Gemini AI
        prompt = f"""
        You are an incredibly strict ATS software. 
        Review the following resume and output strictly in JSON format.
        Do not include markdown or backticks.
        Format required:
        {{
            "ats_score": 64.0,
            "strengths": "Point 1. Point 2.",
            "weaknesses": "Point 1. Point 2."
        }}

        Resume Text:
        {extracted_text}
        """
        response = ai_model.generate_content(prompt)
        
        # Parse the response to extract JSON data
        raw_text = response.text.replace("```json", "").replace("```", "").strip()
        evaluation_data = json.loads(raw_text)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI processing failed: {str(e)}")
    
    try:
        # Store the evaluation in the database
        new_evaluation = models.ResumeEvaluation(
            user_id=user_id,
            file_name=file.filename,
            original_text=extracted_text,
            ats_score=evaluation_data["ats_score"],
            strengths=evaluation_data["strengths"],
            weaknesses=evaluation_data["weaknesses"]
        )
        db.add(new_evaluation)
        db.commit()
        db.refresh(new_evaluation)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    # --- PASTE STEP 3 CODE SINI ---
    try:
        # Deduct 1 from the user's AI quota
        user_data.ai_quota -= 1
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update user quota: {str(e)}")
    # ------------------------------
    
    return {
        "status": "Success",
        "message": "Evaluation safely stored in database",
        "data": evaluation_data
    }

# 6. Fetch Evaluation History (GET) 
@app.get("/users/{user_id}/evaluations/", response_model=List[schemas.ResumeEvaluationResponse])
def get_user_evaluations(user_id: int, db: Session = Depends(get_db)):
    # Query MySQL to find all records matching the given user ID
    evaluations = db.query(models.ResumeEvaluation).filter(models.ResumeEvaluation.user_id == user_id).all()
    
    # If no records are found, return a 404 Not Found error
    if not evaluations:
        raise HTTPException(status_code=404, detail="No evaluation records found for this user")
    
    return evaluations

@app.post("/improve-resume/{evaluation_id}")
def generate_improved_resume(evaluation_id: int, db: Session = Depends(get_db)):
    # 1. Fetch the previous evaluation from the database
    evaluation = db.query(models.ResumeEvaluation).filter(models.ResumeEvaluation.id == evaluation_id).first()
    
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation record not found")
        
    # 2. Check user quota before proceeding
    user_data = db.query(models.User).filter(models.User.id == evaluation.user_id).first()
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
        
    if user_data.ai_quota <= 0:
        raise HTTPException(status_code=429, detail="Your AI trial quota has been exhausted.")
        
    try:
        # 3. Instruct the Co-pilot model
        prompt = f"""
        You are an expert career mentor and resume writer.
        Your task is to rewrite the provided original resume in a highly professional HTML format, fixing the identified weaknesses.

        CRITICAL RULES:
        1. DO NOT invent, hallucinate, or add any fake jobs, companies, degrees, or experiences.
        2. Strictly use ONLY the facts, experiences, and skills provided in the Original Resume Text.
        3. Output ONLY the raw HTML code. Do not include markdown formatting like ```html.

        ATS Weaknesses to fix: {evaluation.weaknesses}

        Original Resume Text:
        {evaluation.original_text}
        """
        
        response = copilot_model.generate_content(prompt)
        improved_html = response.text.replace("```html", "").replace("```", "").strip()
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Co-pilot generation failed: {str(e)}")
        
    # 4. Deduct quota after successful generation
    try:
        user_data.ai_quota -= 1
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update user quota: {str(e)}")
        
    return {
        "status": "Success",
        "message": "Resume successfully rewritten",
        "improved_html": improved_html
    }

@app.post("/export-pdf/")
def export_pdf(data: HTMLInput):
    try:
        # Check OS: Use C:\ for Windows (Local), and /usr/bin/ for Linux (Render)
        import platform
        if platform.system() == "Windows":
            path_wkhtmltopdf = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
        else:
            path_wkhtmltopdf = '/usr/bin/wkhtmltopdf'
            
        config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)
        
        # Convert HTML text to a PDF file (in-memory bytes)
        pdf_bytes = pdfkit.from_string(data.html_content, False, configuration=config)
        
        # Return the PDF file directly to the web browser
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=Improved_Resume.pdf"}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")