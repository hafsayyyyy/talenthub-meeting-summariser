
import json
import logging
import os
import sqlite3
import urllib.error
import urllib.request
import io
import zipfile

import pandas as pd
from fastapi.responses import StreamingResponse
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
    version="1.2.0",
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

    except sqlite3.Error as exc:
        logger.exception("Database health check failed.")
        raise HTTPException(
            status_code=503,
            detail="Database connection failed.",
        ) from exc


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
# Demo summary
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


# --------------------------------------------------
# POST /batch - Batch CSV summarisation
# --------------------------------------------------

@app.post("/batch")
async def batch_summarise(file: UploadFile = File(...)):
    """
    Accept a CSV containing a 'transcript' column and return a ZIP file
    containing individual JSON summaries plus combined JSON and CSV results.
    Successful summaries are also saved to the existing SQLite database.
    """

    filename = file.filename or ""

    if not filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Please upload a CSV file.",
        )

    try:
        raw_data = await file.read()

        if not raw_data:
            raise HTTPException(
                status_code=400,
                detail="The uploaded CSV file is empty.",
            )

        try:
            dataframe = pd.read_csv(io.BytesIO(raw_data))
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail="Could not read the CSV file. Please check its format.",
            ) from exc

        # Allow spaces and capitalisation in column names.
        dataframe.columns = [
            str(column).strip().lower()
            for column in dataframe.columns
        ]

        if "transcript" not in dataframe.columns:
            raise HTTPException(
                status_code=400,
                detail="CSV must contain a 'transcript' column.",
            )

        if dataframe.empty:
            raise HTTPException(
                status_code=400,
                detail="The CSV contains no meeting rows.",
            )

        demo_mode = (
            os.getenv("DEMO_MODE", "false").strip().lower() == "true"
        )

        results = []

        for index, row in dataframe.iterrows():
            raw_transcript = row.get("transcript")

            if pd.isna(raw_transcript):
                transcript = ""
            else:
                transcript = str(raw_transcript).strip()

            result = {
                "row": int(index) + 1,
                "meeting_id": None,
                "transcript": transcript,
                "summary": "",
                "timestamp": None,
                "error": None,
            }

            if not transcript:
                result["error"] = "Transcript is empty."
                results.append(result)
                continue

            try:
                if demo_mode:
                    summary = generate_demo_summary(transcript)
                else:
                    summary = generate_summary(None, transcript)

                meeting_id, timestamp = save_meeting(
                    transcript,
                    summary,
                )

                result["meeting_id"] = meeting_id
                result["summary"] = summary
                result["timestamp"] = timestamp

            except HTTPException as exc:
                result["error"] = str(exc.detail)

            except Exception:
                logger.exception(
                    "Batch summarisation failed for CSV row %s.",
                    index + 1,
                )
                result["error"] = "Could not summarise this transcript."

            results.append(result)

        output = io.BytesIO()

        csv_results = [
            {
                "row": item["row"],
                "meeting_id": item["meeting_id"],
                "summary": item["summary"],
                "timestamp": item["timestamp"],
                "error": item["error"],
            }
            for item in results
        ]

        csv_output = io.StringIO()
        pd.DataFrame(csv_results).to_csv(
            csv_output,
            index=False,
        )

        with zipfile.ZipFile(
            output,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:

            archive.writestr(
                "batch_results.json",
                json.dumps(
                    results,
                    indent=2,
                    ensure_ascii=False,
                ),
            )

            archive.writestr(
                "batch_results.csv",
                csv_output.getvalue(),
            )

            for item in results:
                archive.writestr(
                    f"summaries/meeting_{item['row']:03d}.json",
                    json.dumps(
                        item,
                        indent=2,
                        ensure_ascii=False,
                    ),
                )

        output.seek(0)

        return StreamingResponse(
            output,
            media_type="application/zip",
            headers={
                "Content-Disposition":
                    'attachment; filename="batch_results.zip"',
            },
        )

    finally:
        await file.close()
