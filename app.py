
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from jsonschema import validate, ValidationError
from openai import OpenAI
from pydantic import BaseModel

load_dotenv()

app = FastAPI(
    title="TalentHub Meeting Summariser API",
    description="API for summarising meeting transcripts.",
    version="1.0.0",
)

DATABASE_PATH = os.getenv("DATABASE_PATH", "talenthub.db")

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "minLength": 1}
    },
    "required": ["summary"],
    "additionalProperties": False,
}


class SummaryResponse(BaseModel):
    meeting_id: int
    summary: str
    timestamp: str


def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)
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


@app.get("/")
def home():
    return {
        "message": "TalentHub Meeting Summariser API is running",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


def get_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="OpenAI API key is not configured.",
        )
    return OpenAI(api_key=api_key)


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


def generate_summary(client, transcript: str) -> str:
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "Summarise the meeting transcript as concise bullet points. "
                    "Include key discussion points, decisions, and action items "
                    "when available. Do not invent information. "
                    'Return valid JSON in this format: '
                    '{"summary": "• First point\\n• Second point"}'
                ),
            },
            {"role": "user", "content": transcript},
        ],
        temperature=0.3,
    )

    content = response.choices[0].message.content
    if not content:
        raise HTTPException(
            status_code=502,
            detail="The summarisation service returned no summary.",
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


@app.post("/summarise", response_model=SummaryResponse)
def summarise_meeting(
    transcript: str | None = Form(default=None),
    audio: UploadFile | None = File(default=None),
):
    transcript = transcript.strip() if transcript else None
    if not transcript:
        transcript = None

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

    client = get_client()

    try:
        if audio:
            transcript = transcribe_audio(client, audio)

        summary = generate_summary(client, transcript)
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

        return SummaryResponse(
            meeting_id=meeting_id,
            summary=summary,
            timestamp=timestamp,
        )

    except HTTPException:
        raise
    except Exception:
        logging.exception("Meeting summarisation failed.")
        raise HTTPException(
            status_code=502,
            detail="Unable to process the meeting at this time.",
        )
    finally:
        if audio:
            audio.file.close()
