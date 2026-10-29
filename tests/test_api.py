import http.server
import shutil
import subprocess
import tempfile
import threading

import pytest

from conftest import make_pdf


def upload(client, name="resume.pdf", content=None):
    content = make_pdf("Jane Doe, Data Analyst, Python and SQL") if content is None else content
    return client.post("/upload-resume/", files={"file": (name, content, "application/pdf")})


# ---------- /upload-resume/ ----------

def test_upload_scores_a_resume(client, gemini):
    r = upload(client)
    assert r.status_code == 200
    body = r.json()
    assert body["data"] == {"ats_score": 72.0, "strengths": "Clear layout.", "weaknesses": "No numbers."}
    assert "Jane Doe" in gemini.prompts[-1]  # the PDF text reached the prompt


def test_upload_accepts_uppercase_extension(client, gemini):
    assert upload(client, name="Resume.PDF").status_code == 200


def test_upload_rejects_other_files(client, gemini):
    r = client.post("/upload-resume/", files={"file": ("resume.docx", b"not a pdf", "application/octet-stream")})
    assert r.status_code == 400


def test_upload_rejects_pdf_with_no_text(client, gemini):
    r = upload(client, content=make_pdf(None))
    assert r.status_code == 400
    assert "No text found" in r.json()["detail"]
    assert gemini.prompts == []  # Gemini is never asked to score an empty page


def test_upload_rejects_broken_pdf(client, gemini):
    r = upload(client, content=b"%PDF-1.4 this is not really a pdf")
    assert r.status_code == 400


def test_upload_rejects_files_over_5_mb(client, gemini):
    r = upload(client, content=b"%PDF" + b"0" * (5 * 1024 * 1024 + 1))
    assert r.status_code == 413


def test_upload_strips_markdown_fences(client, gemini):
    gemini.reply = '```json\n{"ats_score": "55", "strengths": "A.", "weaknesses": "B."}\n```'
    r = upload(client)
    assert r.status_code == 200
    assert r.json()["data"]["ats_score"] == 55.0


@pytest.mark.parametrize("reply", [
    "Sorry, I cannot help with that.",
    '{"score": 50}',
    '{"ats_score": 150, "strengths": "A.", "weaknesses": "B."}',
    '[1, 2, 3]',
])
def test_upload_reports_bad_ai_replies(client, gemini, reply):
    gemini.reply = reply
    r = upload(client)
    assert r.status_code == 502
    assert r.json()["detail"].startswith("AI returned an unexpected format")


# ---------- /evaluations/{id} ----------

def test_get_evaluation_does_not_return_resume_text(client, gemini):
    evaluation_id = upload(client).json()["id"]
    body = client.get(f"/evaluations/{evaluation_id}").json()
    assert body["ats_score"] == 72.0
    assert "original_text" not in body


def test_get_unknown_evaluation_is_404(client, gemini):
    assert client.get("/evaluations/999999").status_code == 404


# ---------- /improve-resume/{id} ----------

def test_improve_sends_weaknesses_and_original_text(client, gemini):
    evaluation_id = upload(client).json()["id"]
    gemini.reply = "```html\n<div>Improved</div>\n```"
    r = client.post(f"/improve-resume/{evaluation_id}")
    assert r.status_code == 200
    assert r.json()["improved_html"] == "<div>Improved</div>"
    assert "No numbers." in gemini.prompts[-1]
    assert "Jane Doe" in gemini.prompts[-1]


def test_improve_unknown_evaluation_is_404(client, gemini):
    assert client.post("/improve-resume/999999").status_code == 404


# ---------- /export-pdf/ ----------

needs_wkhtmltopdf = pytest.mark.skipif(shutil.which("wkhtmltopdf") is None, reason="wkhtmltopdf not installed")


def pdf_text(pdf_bytes):
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(pdf_bytes)
        f.flush()
        return subprocess.run(["pdftotext", f.name, "-"], capture_output=True, text=True).stdout


@needs_wkhtmltopdf
def test_export_pdf_returns_a_pdf(client):
    r = client.post("/export-pdf/", json={"html_content": "<h1>Jane Doe</h1><p>Data Analyst</p>"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    if shutil.which("pdftotext"):
        assert "Jane Doe" in pdf_text(r.content)


@needs_wkhtmltopdf
def test_export_pdf_does_not_fetch_internal_urls(client, tmp_path):
    (tmp_path / "secret.txt").write_text("INTERNAL-ONLY-DATA")

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(tmp_path), **kwargs)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Quiet)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/secret.txt"
    try:
        html = f'<p>Resume</p><iframe src="{url}" width="600" height="100"></iframe><img src="{url}">'
        r = client.post("/export-pdf/", json={"html_content": html})
    finally:
        server.shutdown()
    # wkhtmltopdf refuses the request, so the export either fails or comes
    # back without the internal file. It must never contain it.
    assert r.status_code in (200, 500)
    if r.status_code == 200 and shutil.which("pdftotext"):
        assert "INTERNAL-ONLY-DATA" not in pdf_text(r.content)
    assert "INTERNAL-ONLY-DATA" not in r.text


@needs_wkhtmltopdf
def test_export_pdf_does_not_read_local_files(client, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("LOCAL-SERVER-FILE")
    r = client.post("/export-pdf/", json={"html_content": f'<p>Resume</p><iframe src="file://{secret}"></iframe>'})
    assert r.status_code in (200, 500)
    if r.status_code == 200 and shutil.which("pdftotext"):
        assert "LOCAL-SERVER-FILE" not in pdf_text(r.content)
    assert "LOCAL-SERVER-FILE" not in r.text
