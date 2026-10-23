# TalentHub Meeting Summariser API

A FastAPI application that summarises meeting transcripts, optionally transcribes MP3/WAV audio using OpenAI Whisper, validates summary JSON, and stores meetings in SQLite.

## Features

- FastAPI REST API
- `POST /summarise` accepts transcript text or an MP3/WAV audio file
- OpenAI-powered meeting summaries in bullet-point format
- JSON Schema validation for generated summaries
- SQLite storage for original transcripts, summaries, and timestamps
- Response includes `meeting_id`, `summary`, and `timestamp`
- Interactive API documentation at `/docs`
- Automated tests using pytest

## Requirements

- Python 3.11 or compatible version
- An OpenAI API key for real AI summarisation and audio transcription

## Installation

1. Clone the repository and open its folder.
2. Create and activate a virtual environment:

   **Windows PowerShell**

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Create a `.env` file in the project root and add your API key:

   ```text
   OPENAI_API_KEY=your_openai_api_key
   ```

   Never commit `.env` or share your API key publicly.

## Run the API

```powershell
python -m uvicorn app:app --reload
```

Open `http://127.0.0.1:8000/docs` in a browser to explore and test the endpoints.

## API Endpoints

- `GET /` — Home endpoint
- `GET /health` — Health check
- `POST /summarise` — Summarises a transcript or uploaded MP3/WAV audio file

The summarisation endpoint accepts multipart form data. Supply either `transcript` text or an `audio` file.

A successful response contains:

```json
{
  "meeting_id": 1,
  "summary": "- First key point\n- Second key point",
  "timestamp": "UTC timestamp"
}
```

## Database

The application creates an SQLite database named `talenthub.db` by default. It stores each original transcript, generated summary, and timestamp.

Set `DATABASE_PATH` in the environment to use a different database path.

## Run Tests

```powershell
python -m pytest -q
```

The automated tests use a mocked summary for the successful summarisation test, so the test suite can run without making a real OpenAI API request.

## API Key and Costs

A valid OpenAI API key with appropriate API access is required for real summarisation and audio transcription. API usage may incur charges. Do not put your API key in source code or commit it to GitHub.
