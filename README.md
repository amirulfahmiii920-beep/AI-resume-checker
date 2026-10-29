# AI Resume Checker API

A FastAPI backend that reads a PDF resume, scores it the way an Applicant Tracking System
(ATS) would, lists its strengths and weaknesses, rewrites it to fix those weaknesses, and
exports the rewrite as a clean PDF. The scoring and the rewrite are done by Google Gemini.

## What it does

| Step | Endpoint | Result |
|---|---|---|
| 1. Score | `POST /upload-resume/` | Reads the PDF text, asks Gemini for an ATS score out of 100 with strengths and weaknesses, and saves the result |
| 2. Look up | `GET /evaluations/{id}` | The saved score, strengths and weaknesses |
| 3. Rewrite | `POST /improve-resume/{id}` | Gemini rewrites the original resume as HTML in a fixed one-column layout, fixing the saved weaknesses |
| 4. Export | `POST /export-pdf/` | Turns that HTML into a downloadable PDF with `wkhtmltopdf` |

## How it works

```mermaid
sequenceDiagram
    participant C as Client
    participant A as FastAPI
    participant G as Gemini
    participant D as MySQL (Aiven)
    participant W as wkhtmltopdf

    C->>A: POST /upload-resume/ (PDF)
    A->>A: Extract text with PyPDF2
    A->>G: Score this resume, reply in JSON
    G-->>A: ats_score, strengths, weaknesses
    A->>D: Save file name, text, score, feedback
    A-->>C: id + score and feedback

    C->>A: POST /improve-resume/{id}
    A->>D: Load original text and weaknesses
    A->>G: Rewrite as HTML, fix these weaknesses
    G-->>A: Resume HTML
    A-->>C: improved_html

    C->>A: POST /export-pdf/ (HTML)
    A->>W: Render HTML, no file or network access
    W-->>A: PDF bytes
    A-->>C: Improved_Resume.pdf
```

### Two models, two jobs

| Job | Model | Why |
|---|---|---|
| Scoring | `gemini-3.5-flash` | Needs careful judgement and a strict JSON reply |
| Rewriting | `gemini-3.5-flash-lite` | Longer output that follows a fixed template, so a lighter model is enough |

### Guarding the AI reply

Gemini is asked for JSON with no markdown, but replies are still checked before anything is
saved. Markdown fences are stripped, the reply must be a JSON object with `ats_score`,
`strengths` and `weaknesses`, and the score must be a number from 0 to 100 (a string such as
`"55"` is accepted). Anything else returns **502 AI returned an unexpected format** instead of
a misleading database error.

### Rewrite rules

The rewrite prompt tells the model not to invent jobs, companies, degrees or experience, to use
only facts from the original resume, to output raw HTML with all text black in Arial, and to
follow a fixed section order: Summary, Core Technical Skills, Academic Qualification, Key
Project Experience, Professional Experiences, Referees.

### Database

One table, `resume_evaluations`:

| Column | Type | Notes |
|---|---|---|
| `id` | Integer | Primary key |
| `file_name` | String(255) | Name of the uploaded PDF |
| `original_text` | Text | Extracted resume text, used by the rewrite. Never returned by the API |
| `ats_score` | Float | 0 to 100 |
| `strengths`, `weaknesses` | Text | Gemini's feedback |

## Testing

`pytest` runs 18 tests in `tests/test_api.py`. Gemini is replaced with a fake model and MySQL
with a throwaway SQLite file, so no API key, network or database is needed. PDFs are generated
in the test with reportlab.

| Area | What is checked |
|---|---|
| Upload | A normal resume is scored and its text reaches the prompt; `Resume.PDF` is accepted; other files, broken PDFs, image-only PDFs and files over 5 MB are rejected |
| AI reply | Markdown fences are stripped; plain text, missing keys, a score of 150 and a JSON list all return 502 |
| Look up | The reply has the score and feedback but no resume text; unknown ids return 404 |
| Rewrite | The prompt carries the saved weaknesses and the original text; unknown ids return 404 |
| Export | A real PDF comes back; HTML pointing at an internal URL or a local file cannot pull that content into the PDF |

All 18 pass on Python 3.11 with wkhtmltopdf 0.12.6. The export tests are skipped when
wkhtmltopdf is not installed.

### Fixed after a code review

The same tests were run against the code before these fixes, and 11 of the 18 failed.

| Problem | Evidence | Fix |
|---|---|---|
| `GET /evaluations/{id}` returned the whole resume text | Ids are 1, 2, 3 and so on, so anyone could read other people's resumes, phone numbers and addresses by counting up | The endpoint now uses `ResumeEvaluationResponse`, which has no `original_text` |
| `/export-pdf/` could fetch internal URLs (SSRF) | HTML with an iframe pointing at a server on `127.0.0.1` produced a PDF containing that server's file | wkhtmltopdf now runs with local file access off, JavaScript off and all network requests sent to a dead proxy |
| Image-only PDFs crashed or were scored anyway | `extract_text()` returns `None` for image pages, and a blank page was sent to Gemini and still got a score | Missing page text counts as empty, and a PDF with no text returns 400 |
| `Resume.PDF` was rejected | The extension check was case-sensitive | The check ignores case |
| Bad Gemini replies looked like database errors | A reply without `ats_score` returned "Database error: 'ats_score'" | The reply is validated first (see above) and returns 502 |
| A broken PDF returned 500 | Unreadable files were reported as a server error | Returns 400, since the file is the problem |
| No upload size limit | Any size was read into memory | Uploads over 5 MB return 413 |
| Scoring blocked the whole server | `upload_resume` is async but called Gemini synchronously, so every other request waited | Uses `generate_content_async` |
| Docker port did not match | `EXPOSE 8000` but uvicorn listened on 10000 | Listens on `$PORT` (10000 by default, as Render expects) |

## Run it

1. Install Python 3.10 or newer and [wkhtmltopdf](https://wkhtmltopdf.org/downloads.html).
2. Clone and install:

   ```bash
   git clone https://github.com/amirulfahmiii920-beep/AI-resume-checker.git
   cd AI-resume-checker
   python -m venv venv
   venv\Scripts\activate        # Windows
   source venv/bin/activate     # macOS and Linux
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and fill it in:

   ```env
   GEMINI_API_KEY=your_gemini_api_key
   DATABASE_URL=mysql+pymysql://user:password@host:port/defaultdb
   ```

   Get a key from [Google AI Studio](https://aistudio.google.com/). Any SQLAlchemy URL works
   for local use, for example `sqlite:///./local.db`.

4. Start the server and open the Swagger UI at http://127.0.0.1:8000/docs:

   ```bash
   uvicorn main:app --reload
   ```

5. Run the tests:

   ```bash
   pip install -r requirements-dev.txt
   pytest
   ```

### Deploy on Render

The `Dockerfile` installs wkhtmltopdf on Debian bullseye and starts uvicorn on Render's `$PORT`.
Set `GEMINI_API_KEY` and `DATABASE_URL` in the Render environment.

## Project structure

```
main.py              endpoints, Gemini prompts, reply checks, PDF export
models.py            SQLAlchemy model for resume_evaluations
schemas.py           Pydantic response model
tests/
  conftest.py        fake Gemini, SQLite database, PDF helper
  test_api.py        18 endpoint tests
requirements.txt     runtime packages
requirements-dev.txt test packages
Dockerfile           Render image with wkhtmltopdf
```

## Limitations

- **No login.** Anyone who can reach the API can score or rewrite resumes and spend the Gemini
  quota, and evaluation ids can be guessed. A random id (UUID) or a per-user token would stop
  people from rewriting other people's saved resumes through `/improve-resume/{id}`.
- **Resume text is stored in the database**, so it should be deleted after a set time.
- **Database SSL does not check the certificate** (`cert_reqs: 0`). Using Aiven's CA
  certificate would close that gap.
- **Export does not load images or styles from other sites.** The block that stops SSRF also
  stops these, so an export with an external image fails with 500. The rewrite template uses
  only inline styles, so it is not affected.
- **The rewrite prompt has rules written for one resume**, for example describing mobile work
  as Android only. They should be removed or made optional before other people use it.
- **`google-generativeai` is no longer maintained.** Google recommends moving to the
  `google-genai` package.
- **Package versions are not pinned** in `requirements.txt`.

## Built with

Python, FastAPI, Uvicorn, SQLAlchemy, PyMySQL, Aiven MySQL, Google Gemini
(`google-generativeai`), PyPDF2, pdfkit, wkhtmltopdf, pytest.
