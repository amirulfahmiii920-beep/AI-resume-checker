import io
import os
import json
from typing import List
from fastapi import FastAPI, Depends, HTTPException, File, UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from PyPDF2 import PdfReader
from dotenv import load_dotenv
from fastapi.responses import Response
from pydantic import BaseModel
import google.generativeai as genai
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
ai_model = genai.GenerativeModel("gemini-3.7-flash")

# Initialize the Co-pilot model for rewriting
copilot_model = genai.GenerativeModel("gemini-3.6-flash")

# 3. Database setup
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(
    DATABASE_URL,
    connect_args={"ssl": {"check_hostname": False, "cert_reqs": 0}}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Create tables based on the existing models
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 4. API upload resume and evaluate
@app.post("/upload-resume/")
async def upload_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
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
        # Store the evaluation in the database (without user ID and quota)
        new_evaluation = models.ResumeEvaluation(
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

    # Return the evaluation result
    return {
        "status": "Success",
        "id": new_evaluation.id,
        "data": evaluation_data
    }

# 5. API get evaluation by ID
@app.get("/evaluations/{evaluation_id}")
def get_evaluation(evaluation_id: int, db: Session = Depends(get_db)):
    evaluation = db.query(models.ResumeEvaluation).filter(models.ResumeEvaluation.id == evaluation_id).first()
    
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation record not found")
        
    return evaluation

# 6. API repair & improve resume
@app.post("/improve-resume/{evaluation_id}")
def generate_improved_resume(evaluation_id: int, db: Session = Depends(get_db)):
    evaluation = db.query(models.ResumeEvaluation).filter(models.ResumeEvaluation.id == evaluation_id).first()
    
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation record not found")
        
    try:
        # Instruct the Co-pilot model
        prompt = f"""
        You are an expert career mentor and resume writer.
        Your task is to rewrite the provided original resume in a highly professional HTML format, fixing the identified weaknesses.

        CRITICAL RULES:
        1. DO NOT invent, hallucinate, or add any fake jobs, companies, degrees, or experiences.
        2. Strictly use ONLY the facts, experiences, and skills provided in the Original Resume Text.
        3. Output ONLY the raw HTML code. Do not include markdown formatting.
        4. STRICTLY DO NOT use any emojis. Use standard text and professional bullet points only.
        5. When rewriting details about mobile application development, ensure it is exclusively described for the Android platform. Avoid writing it as cross-platform.
        6. Do not use the abbreviation "e.g." or semicolons in the middle of sentences.

        HTML AND CSS FORMATTING RULES:
        1. Apply inline CSS styling to ensure ALL text, including headings and links, is STRICTLY BLACK (#000000). 
        2. Use Arial, Helvetica, or a similar professional sans-serif font.
        3. The layout MUST exactly mimic the following structure and sequence, replacing the bracketed text with the optimized content:

        <div style="font-family: Arial, sans-serif; font-size: 11pt; line-height: 1.4;">
            <div style="text-align: center; font-weight: bold; font-size: 14pt; text-transform: uppercase;">[FULL NAME]</div>
            <div style="text-align: center; font-size: 10pt;">Phone: [Phone] | Email: [Email] | LinkedIn: [LinkedIn] | GitHub: [GitHub]</div>
            <div style="text-align: center; font-size: 10pt; margin-bottom: 15px;">Address: [Address]</div>
            
            <h3 style="text-transform: uppercase; font-size: 12pt; border-bottom: 1px solid black; padding-bottom: 2px; margin-bottom: 5px;">SUMMARY</h3>
            <p style="margin-top: 0;">[Improved paragraph summary fixing the weaknesses, strictly in one paragraph]</p>

            <h3 style="text-transform: uppercase; font-size: 12pt; border-bottom: 1px solid black; padding-bottom: 2px; margin-bottom: 5px;">CORE TECHNICAL SKILLS</h3>
            <p style="margin-top: 0; margin-bottom: 0;"><strong>[Category 1]:</strong> [Comma-separated skills]</p>
            <p style="margin-top: 0; margin-bottom: 0;"><strong>[Category 2]:</strong> [Comma-separated skills]</p>

            <h3 style="text-transform: uppercase; font-size: 12pt; border-bottom: 1px solid black; padding-bottom: 2px; margin-top: 15px; margin-bottom: 5px;">ACADEMIC QUALIFICATION</h3>
            <p style="margin-top: 0; margin-bottom: 2px;"><strong>[Month Year - Month Year]: [Degree], [University]</strong></p>
            <ul style="margin-top: 0;">
                <li>[Improved bullet points focusing on final year projects and key achievements]</li>
            </ul>

            <h3 style="text-transform: uppercase; font-size: 12pt; border-bottom: 1px solid black; padding-bottom: 2px; margin-bottom: 5px;">KEY PROJECT EXPERIENCE</h3>
            <p style="margin-top: 0; margin-bottom: 2px;"><strong>[Project Name 1]</strong></p>
            <ul style="margin-top: 0; margin-bottom: 10px;">
                <li>[Improved bullet points focusing on impact and tools used]</li>
            </ul>

            <h3 style="text-transform: uppercase; font-size: 12pt; border-bottom: 1px solid black; padding-bottom: 2px; margin-bottom: 5px;">PROFESSIONAL EXPERIENCES</h3>
            <p style="margin-top: 0; margin-bottom: 2px;"><strong>[Month Year - Month Year]: [Job Title], [Company]</strong></p>
            <ul style="margin-top: 0; margin-bottom: 10px;">
                <li>[Improved bullet points focusing on achievements]</li>
            </ul>

            <h3 style="text-transform: uppercase; font-size: 12pt; border-bottom: 1px solid black; padding-bottom: 2px; margin-bottom: 5px;">REFEREES</h3>
            <p style="margin-top: 0; margin-bottom: 0;"><strong>[Referee Name 1]</strong></p>
            <p style="margin-top: 0; margin-bottom: 0;">[Title], [Company]</p>
            <p style="margin-top: 0; margin-bottom: 10px;">Phone No: [Phone]</p>
        </div>

        ATS Weaknesses to fix: {evaluation.weaknesses}

        Original Resume Text:
        {evaluation.original_text}
        """
        
        response = copilot_model.generate_content(prompt)
        improved_html = response.text.replace("```html", "").replace("```", "").strip()
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Co-pilot generation failed: {str(e)}")
        
    return {
        "status": "Success",
        "message": "Resume successfully rewritten",
        "improved_html": improved_html
    }

# 7. API export PDF
@app.post("/export-pdf/")
def export_pdf(data: HTMLInput):
    try:
        if platform.system() == "Windows":
            path_wkhtmltopdf = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
        else:
            path_wkhtmltopdf = '/usr/bin/wkhtmltopdf'
            
        config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)
        pdf_bytes = pdfkit.from_string(data.html_content, False, configuration=config)
        
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=Improved_Resume.pdf"}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")