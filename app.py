
import json
import logging
import os
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from jsonschema import validate, ValidationError
from openai import OpenAI
from pydantic import BaseModel


# --------------------------------------------------
# Configuration
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
ENV_FILE = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_FILE, override=True)

DATABASE_PATH = Path(
    os.getenv("DATABASE_PATH", str(BASE_DIR / "talenthub.db"))
)

OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "http://127.0.0.1:11434/api/generate",
)

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama2")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="TalentHub Meeting Summariser API",
    description="API for summarising meeting transcripts using local AI.",
    version="1.1.0",
)

app.mount(
    "/static",
    StaticFiles(directory=str(STATIC_DIR), check_dir=False),
    name="static",
)


# --------------------------------------------------
# Summary JSON schema
# --------------------------------------------------

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "minLength": 1,
        }
    },
    "required": ["summary"],
    "additionalProperties": False,
}


class SummaryResponse(BaseModel):
    meeting_id: int
    summary: str
    timestamp: str


# --------------------------------------------------
# SQLite database
# --------------------------------------------------

def get_connection():
    connection = sqlite3.connect(str(DATABASE_PATH))
    connection.row_factory = sqlite3.Row
    return connection


def initialise_database():
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS meetings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transcript TEXT NOT NULL,
                summary TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
            """
        )


initialise_database()


def save_meeting(transcript: str, summary: str):
    timestamp = datetime.now(timezone.utc).isoformat()

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO meetings (transcript, summary, timestamp)
            VALUES (?, ?, ?)
            """,
            (transcript, summary, timestamp),
        )
        meeting_id = cursor.lastrowid

    return meeting_id, timestamp


# --------------------------------------------------
# Dashboard
# --------------------------------------------------

@app.get("/")
def home():
    index_file = STATIC_DIR / "index.html"

    if not index_file.is_file():
        raise HTTPException(
            status_code=500,
            detail="Dashboard file static/index.html was not found.",
        )

    return FileResponse(index_file)


# --------------------------------------------------
# Health check
# --------------------------------------------------

@app.get("/health")
def health():
    try:
        with get_connection() as connection:
            connection.execute("SELECT 1")

        return {
            "status": "healthy",
            "database": "connected",
            "ai_provider": "ollama",
            "model": OLLAMA_MODEL,
        }

    except sqlite3.Error:
        logger.exception("Database health check failed.")
        raise HTTPException(
            status_code=503,
            detail="Database connection failed.",
        )


# --------------------------------------------------
# OpenAI client for audio transcription only
# --------------------------------------------------

def get_client():
    api_key = os.getenv("OPENAI_API_KEY", "").strip()

    if not api_key or api_key == "your_actual_api_key_here":
        raise HTTPException(
            status_code=503,
            detail=(
                "Audio transcription requires a valid OpenAI API key "
                "and available API credits."
            ),
        )

    try:
        return OpenAI(api_key=api_key)

    except Exception as exc:
        logger.exception("Could not initialise OpenAI client.")
        raise HTTPException(
            status_code=503,
            detail="Could not initialise the audio transcription service.",
        ) from exc


# --------------------------------------------------
# Demo summary (optional)
# --------------------------------------------------

def generate_demo_summary(transcript: str) -> str:
    """Generate a clearly labelled non-AI demo summary."""

    text = transcript.strip()

    if not text:
        raise HTTPException(
            status_code=422,
            detail="The transcript is empty.",
        )

    sentences = [
        part.strip()
        for part in text.replace("\n", " ").split(".")
        if part.strip()
    ]

    if not sentences:
        sentences = [text]

    bullet_points = "\n".join(
        f"- {point}" for point in sentences[:5]
    )

    return (
        "DEMO MODE - This is not an AI-generated summary.\n"
        + bullet_points
    )


# --------------------------------------------------
# Local AI summary using Ollama
# --------------------------------------------------

def generate_summary(client, transcript: str) -> str:
    """Generate and validate an AI summary using local Ollama."""

    if not transcript or not transcript.strip():
        raise HTTPException(
            status_code=422,
            detail="The transcript is empty.",
        )

    prompt = f"""
You are a professional meeting summarisation assistant.

Summarise the meeting transcript accurately and concisely.
Include the following when available:
1. Key discussion points
2. Decisions made
3. Action items and responsible people
4. Deadlines

Do not invent facts or action items.
Return ONLY a valid JSON object with exactly this structure:
{{"summary": "- First key point\\n- Second key point"}}

Meeting transcript:
{transcript}
"""

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.2,
        },
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

        content = result.get("response", "").strip()

        if not content:
            raise HTTPException(
                status_code=502,
                detail="Ollama returned an empty response.",
            )

        data = json.loads(content)
        validate(instance=data, schema=SUMMARY_SCHEMA)

        summary = data["summary"].strip()

        if not summary:
            raise HTTPException(
                status_code=502,
                detail="The AI returned an empty summary.",
            )

        return summary

    except HTTPException:
        raise

    except urllib.error.URLError as exc:
        logger.exception("Could not connect to Ollama.")

        raise HTTPException(
            status_code=503,
            detail=(
                "Could not connect to Ollama. Make sure Ollama is "
                "running and the configured model is installed."
            ),
        ) from exc

    except (json.JSONDecodeError, ValidationError) as exc:
        logger.exception("Ollama returned invalid summary JSON.")

        raise HTTPException(
            status_code=502,
            detail="Ollama returned an invalid summary format.",
        ) from exc

    except TimeoutError as exc:
        logger.exception("Ollama request timed out.")

        raise HTTPException(
            status_code=504,
            detail="Ollama took too long to generate the summary.",
        ) from exc


# --------------------------------------------------
# Audio transcription using OpenAI Whisper
# --------------------------------------------------

def transcribe_audio(client, audio: UploadFile) -> str:
    filename = audio.filename or ""
    extension = Path(filename).suffix.lower()

    if extension not in {".mp3", ".wav"}:
        raise HTTPException(
            status_code=400,
            detail="Only MP3 and WAV audio files are supported.",
        )

    audio_bytes = audio.file.read()

    if not audio_bytes:
        raise HTTPException(
            status_code=400,
            detail="The uploaded audio file is empty.",
        )

    result = client.audio.transcriptions.create(
        model="whisper-1",
        file=(filename, audio_bytes),
    )

    transcript = result.text.strip()

    if not transcript:
        raise HTTPException(
            status_code=422,
            detail="No speech could be transcribed from the audio.",
        )

    return transcript


# --------------------------------------------------
# POST /summarise
# --------------------------------------------------

@app.post("/summarise", response_model=SummaryResponse)
def summarise_meeting(
    transcript: str | None = Form(default=None),
    audio: UploadFile | None = File(default=None),
):
    transcript = transcript.strip() if transcript else None

    if not transcript and not audio:
        raise HTTPException(
            status_code=422,
            detail="Provide transcript text or an MP3/WAV audio file.",
        )

    if transcript and audio:
        raise HTTPException(
            status_code=400,
            detail="Provide transcript text or audio, not both.",
        )

    if audio and not audio.filename:
        raise HTTPException(
            status_code=400,
            detail="The uploaded audio filename is missing.",
        )

    try:
        demo_mode = (
            os.getenv("DEMO_MODE", "false").strip().lower() == "true"
        )

        if audio:
            # Audio still requires OpenAI Whisper.
            client = get_client()
            transcript = transcribe_audio(client, audio)

        if not transcript:
            raise HTTPException(
                status_code=422,
                detail="No transcript was provided.",
            )

        if demo_mode:
            summary = generate_demo_summary(transcript)
        else:
            # Text summaries use local Ollama; no API key is needed.
            summary = generate_summary(None, transcript)

        meeting_id, timestamp = save_meeting(
            transcript,
            summary,
        )

        return SummaryResponse(
            meeting_id=meeting_id,
            summary=summary,
            timestamp=timestamp,
        )

    except HTTPException:
        raise

    except Exception as exc:
        logger.exception("Meeting summarisation failed.")

        raise HTTPException(
            status_code=502,
            detail=(
                "Unable to process the meeting. Check the server "
                "terminal for the underlying error."
            ),
        ) from exc

    finally:
        if audio:
            audio.file.close()


# --------------------------------------------------
# GET /meetings
# --------------------------------------------------

@app.get("/meetings")
def list_meetings():
    try:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT id, transcript, summary, timestamp
                FROM meetings
                ORDER BY id DESC
                """
            ).fetchall()

        return {
            "meetings": [dict(row) for row in rows]
        }

    except sqlite3.Error as exc:
        logger.exception("Could not retrieve saved meetings.")

        raise HTTPException(
            status_code=500,
            detail="Could not retrieve meetings from the database.",
        ) from exc
