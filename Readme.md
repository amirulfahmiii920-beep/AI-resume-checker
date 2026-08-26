# AI-Powered Resume Analyzer API

This is the backend repository for the AI-Powered Resume Analyzer application. Built using FastAPI, this system leverages Google's Gemini AI to evaluate resumes against ATS (Applicant Tracking System) standards, provide constructive feedback, rewrite content for maximum impact, and export the improved resume back into a PDF format.

## Features
*   **PDF Text Extraction:** Seamlessly reads and extracts content from uploaded PDF resumes.
*   **ATS Scoring & Feedback:** Uses Gemini 3.7 Flash to generate an ATS score, highlighting strengths and weaknesses.
*   **AI Resume Rewriting:** Utilizes Gemini 3.6 Flash to professionally rewrite the resume in a clean, ATS-friendly HTML format.
*   **PDF Export:** Converts the newly generated HTML resume back into a downloadable physical PDF using `wkhtmltopdf`.
*   **Quota Management:** Implements a strict database-level quota system to limit API usage per user.
*   **Cloud Database:** Integrated with Aiven Cloud MySQL for remote data persistence.

## Tech Stack
*   **Framework:** FastAPI (Python)
*   **Database:** MySQL (Aiven Cloud) & SQLAlchemy (ORM)
*   **AI Integration:** Google Generative AI SDK (Gemini)
*   **PDF Processing:** PyPDF2 (Reading) & pdfkit / wkhtmltopdf (Writing)
*   **Server:** Uvicorn

## Prerequisites
Before running this project, ensure you have the following installed:
1.  **Python 3.10+**
2.  **wkhtmltopdf:** 
    *   Windows: Download and install from the official website.
    *   Linux/Render: Installed via Dockerfile.
3.  **Google Gemini API Key:** Get it from Google AI Studio.

## Local Setup Instructions

1.  **Clone the repository:**
    ```bash
    git clone <your-github-repo-url>
    cd backend
    ```

2.  **Create a virtual environment:**
    ```bash
    python -m venv venv
    venv\Scripts\activate  # For Windows
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Environment Variables:**
    Create a `.env` file in the root directory and configure it based on the provided `.env.example` file:
    ```env
    GEMINI_API_KEY=your_gemini_api_key_here
    DATABASE_URL=mysql+pymysql://user:password@host:port/defaultdb?ssl-mode=REQUIRED
    ```

5.  **Run the application:**
    ```bash
    uvicorn main:app --reload
    ```

6.  **Access the API Documentation:**
    Open your browser and navigate to `http://127.0.0.1:8000/docs` to interact with the Swagger UI.

## Deployment (Render)
This project is configured for cloud deployment on Render.com. 
*   It includes a `Dockerfile` to automatically configure the Linux environment and install the `wkhtmltopdf` software dependency.
*   It includes a `requirements.txt` file for all Python dependencies.