
import json
import logging
import os
import sqlite3
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="TalentHub Meeting Summariser API",
    description="API for summarising meeting transcripts.",
    version="1.0.0",
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
# Dashboard and health check
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


@app.get("/health")
def health():
    return {"status": "healthy"}


# --------------------------------------------------
# OpenAI client
# --------------------------------------------------

def get_client():
    api_key = os.getenv("OPENAI_API_KEY", "").strip()

    if not api_key or api_key == "your_actual_api_key_here":
        raise HTTPException(
            status_code=503,
            detail="OpenAI API key is missing from the .env file.",
        )

    try:
        return OpenAI(api_key=api_key)
    except Exception:
        logger.exception("Could not initialise OpenAI client.")
        raise HTTPException(
            status_code=503,
            detail="Could not initialise the AI service.",
        )


# --------------------------------------------------
# Demo summary: no OpenAI API credits required
# --------------------------------------------------

def generate_demo_summary(transcript: str) -> str:
    """
    Create a simple demo output without using an AI service.
    The output is clearly labelled as a demo.
    """

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

    points = sentences[:5]

    if not points:
        points = [text]

    bullet_points = "\n".join(
        f"• {point}" for point in points
    )

    return (
        "DEMO MODE — This is not an AI-generated summary.\n"
        + bullet_points
    )


# --------------------------------------------------
# Actual AI summary: requires OpenAI API credits
# --------------------------------------------------

def generate_summary(client, transcript: str) -> str:
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "Summarise the meeting transcript as concise bullet "
                    "points. Include key discussion points, decisions, "
                    "and action items when available. Do not invent "
                    "information. Return valid JSON in this format: "
                    '{"summary": "First point\\nSecond point"}'
                ),
            },
            {
                "role": "user",
                "content": transcript,
            },
        ],
        temperature=0.3,
    )

    content = response.choices[0].message.content

    if not content:
        raise HTTPException(
            status_code=502,
            detail="The AI service returned no summary.",
        )

    try:
        data = json.loads(content)
        validate(instance=data, schema=SUMMARY_SCHEMA)
    except (json.JSONDecodeError, ValidationError):
        raise HTTPException(
            status_code=502,
            detail="The AI returned invalid summary JSON.",
        )

    summary = data["summary"].strip()

    if not summary:
        raise HTTPException(
            status_code=502,
            detail="The summary was empty.",
        )

    return summary


# --------------------------------------------------
# MP3/WAV transcription: requires OpenAI API credits
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

        # Audio transcription requires the real OpenAI service.
        if audio:
            client = get_client()
            transcript = transcribe_audio(client, audio)

        if not transcript:
            raise HTTPException(
                status_code=422,
                detail="No transcript was provided.",
            )

        # Keep demo mode separate from actual AI mode.
        if demo_mode:
            summary = generate_demo_summary(transcript)
        else:
            client = get_client()
            summary = generate_summary(client, transcript)

        meeting_id, timestamp = save_meeting(transcript, summary)

        return SummaryResponse(
            meeting_id=meeting_id,
            summary=summary,
            timestamp=timestamp,
        )

    except HTTPException:
        raise

    except Exception:
        logger.exception("Meeting summarisation failed.")
        raise HTTPException(
            status_code=502,
            detail=(
                "Unable to process the meeting. Check the server "
                "terminal for the underlying error."
            ),
        )

    finally:
        if audio:
            audio.file.close()


# --------------------------------------------------
# GET /meetings: view saved meetings
# --------------------------------------------------

@app.get("/meetings")
def list_meetings():
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
