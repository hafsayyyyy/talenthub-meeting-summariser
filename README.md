# TalentHub Meeting Summariser API

A FastAPI application that summarises meeting transcripts, optionally transcribes MP3/WAV audio using OpenAI Whisper, validates summary JSON, and stores meetings in SQLite.

## Features

- FastAPI REST API
- `POST /summarise` accepts transcript text or an MP3/WAV audio file
- OpenAI-powered meeting summaries in bullet-point format
- Optional demo mode for testing without OpenAI API credits
- JSON Schema validation for AI-generated summaries
- SQLite storage for transcripts, summaries, and timestamps
- `GET /meetings` lists saved meetings
- `GET /health` checks API health
- Interactive API documentation at `/docs`
- Automated tests using pytest

## Requirements

- Python 3.11 or compatible version
- OpenAI API credits for actual AI summarisation and audio transcription

## Installation

1. Clone the repository and open its folder.
2. Create and activate a virtual environment:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Create a `.env` file in the project root:

   ```text
   OPENAI_API_KEY=your_openai_api_key
   OPENAI_MODEL=gpt-4o-mini
   DEMO_MODE=true
   ```

Never commit `.env` or share your API key publicly.

## Run the API

```powershell
python -m uvicorn app:app --reload
```

Open the following URLs in your browser:

- Dashboard: `http://127.0.0.1:8000/`
- API documentation: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/health`
- Saved meetings: `http://127.0.0.1:8000/meetings`

## API Endpoints

- `GET /` — Dashboard
- `GET /health` — Health check
- `POST /summarise` — Summarises transcript text or uploaded audio
- `GET /meetings` — Returns saved meetings from SQLite

The `/summarise` endpoint accepts multipart form data. Provide either the `transcript` field or an `audio` file, not both.

A successful response looks like this:

```json
{
  "meeting_id": 1,
  "summary": "Example meeting summary",
  "timestamp": "UTC timestamp"
}
```

## Demo Mode

Set `DEMO_MODE=true` in `.env` to test transcript submissions without calling the OpenAI API for summarisation.

Demo Mode produces a simple, clearly labelled demonstration output. It is not an AI-generated summary. Text transcript testing works without OpenAI API credits.

MP3/WAV transcription still requires the OpenAI API. To use actual AI summarisation, set `DEMO_MODE=false` and configure an API key with sufficient credits.

## Database

The application creates `talenthub.db` in the project directory by default. Each saved meeting includes its original transcript, summary, and timestamp.

Set `DATABASE_PATH` in the environment to use a different database path.

## Run Tests

```powershell
python -m pytest -q
```

The successful summarisation test uses a mocked summary, so it does not require a real OpenAI API request.

## API Key and Costs

Actual OpenAI summarisation and audio transcription require API access and sufficient credits. API usage may incur charges. A ChatGPT subscription does not automatically provide OpenAI API credits.

Never put your API key in source code or commit it to GitHub.
