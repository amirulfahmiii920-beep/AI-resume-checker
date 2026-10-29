"""Test setup: a fake Gemini model and a throwaway SQLite database.

No API key, no network and no MySQL are needed. Each test sets what the
fake Gemini replies with through the `gemini` fixture.
"""
import io
import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_db_dir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_db_dir, 'test.db')}"
os.environ.setdefault("GEMINI_API_KEY", "test-key")

import google.generativeai as genai  # noqa: E402


class _Reply:
    def __init__(self, text):
        self.text = text


class FakeModel:
    """Stands in for genai.GenerativeModel and records every prompt."""

    reply = '{"ats_score": 72, "strengths": "Clear layout.", "weaknesses": "No numbers."}'
    prompts = []

    def __init__(self, *args, **kwargs):
        pass

    def generate_content(self, prompt):
        FakeModel.prompts.append(prompt)
        return _Reply(FakeModel.reply)

    async def generate_content_async(self, prompt):
        return self.generate_content(prompt)


genai.GenerativeModel = FakeModel

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture
def gemini():
    FakeModel.reply = '{"ats_score": 72, "strengths": "Clear layout.", "weaknesses": "No numbers."}'
    FakeModel.prompts = []
    return FakeModel


def make_pdf(text=None):
    """A one-page PDF with `text` on it, or a blank page when text is None."""
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    page = canvas.Canvas(buffer)
    if text:
        page.drawString(72, 720, text)
    page.showPage()
    page.save()
    return buffer.getvalue()
