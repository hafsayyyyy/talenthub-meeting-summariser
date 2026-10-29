# TalentHub Meeting Summariser

TalentHub is a FastAPI application for summarising recruitment meeting transcripts. It supports individual transcript submissions, local AI summarisation with Ollama, a demonstration mode, batch CSV processing, and SQLite storage.

## Features

- FastAPI REST API with interactive Swagger documentation.
- Recruiter dashboard accessible at `/`.
- `POST /summarise` for individual meeting transcripts.
- Optional MP3/WAV audio transcription using OpenAI.
- Local AI summarisation using Ollama.
- Demo mode for testing without AI summarisation credits.
- JSON validation for summary responses.
- SQLite database for meeting transcripts, summaries, and timestamps.
- `GET /meetings` to retrieve saved meetings.
- `GET /health` to check API health.
- `POST /batch` to process multiple meeting transcripts from a CSV file.
- ZIP download containing batch results in JSON and CSV formats, plus individual meeting summary files.
- Automated tests using pytest.

## Requirements

- Python 3.11 or a compatible Python version.
- Ollama installed and running for local AI summarisation.
- An Ollama model downloaded locally, such as `llama2`.
- An OpenAI API key with sufficient credits if using the audio transcription feature.

## Installation

1. Clone the repository and open the project folder.
2. Create a virtual environment:

   ```powershell
   python -m venv .venv
   ```

3. Activate the environment:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

4. Install the required dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

5. Install and start Ollama, then download the configured model if necessary:

   ```powershell
   ollama pull llama2
   ```

6. Create a `.env` file in the project root. Configure the variables supported by `app.py`:

   ```text
   OLLAMA_URL=http://localhost:11434/api/generate
   OLLAMA_MODEL=llama2
   DEMO_MODE=false
   DATABASE_PATH=talenthub.db
   OPENAI_API_KEY=your_openai_api_key
   ```

   The OpenAI key is required for audio transcription if that feature uses OpenAI Whisper. Keep your actual API key private and never commit `.env` to GitHub.

## Run the Application

Start the FastAPI server:

```powershell
python -m uvicorn app:app --reload
```

Open these URLs in your browser:

- **Recruiter dashboard:** http://127.0.0.1:8000/
- **Swagger API documentation:** http://127.0.0.1:8000/docs
- **Health check:** http://127.0.0.1:8000/health
- **Saved meetings:** http://127.0.0.1:8000/meetings

Keep Ollama running in the background when using local AI summarisation.

## API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | Opens the recruiter dashboard |
| GET | `/health` | Checks API health |
| POST | `/summarise` | Summarises one meeting transcript or processes supported audio |
| GET | `/meetings` | Retrieves saved meeting records |
| POST | `/batch` | Processes multiple transcripts from a CSV upload |

### Individual Meeting Summarisation

The `/summarise` endpoint accepts multipart form data. Provide a transcript or an audio file, according to the endpoint's supported inputs.

A successful response includes the meeting ID, summary, and timestamp.

### Batch CSV Summarisation

The `/batch` endpoint accepts a CSV file containing a `transcript` column.

To test it:

1. Open http://127.0.0.1:8000/docs.
2. Expand `POST /batch`.
3. Click **Try it out**.
4. Upload a CSV file containing a `transcript` column.
5. Click **Execute**.
6. Download the returned ZIP archive.

The ZIP archive contains:

- `batch_results.json` — combined batch results in JSON format.
- `batch_results.csv` — combined batch results in CSV format.
- `summaries/meeting_001.json` — an individual meeting result.
- Additional individual JSON files for other processed meetings.

Batch processing uses the application's configured summarisation mode and stores successfully processed meeting records in SQLite.

## AI and Demo Modes

### Ollama Mode

Set `DEMO_MODE=false` to use the configured Ollama model for local AI summarisation. Ollama must be running and the selected model must be available.

### Demo Mode

Set `DEMO_MODE=true` to test the application without calling the AI summarisation service. The returned demonstration output is not an actual AI-generated summary.

Demo mode is useful for checking the dashboard, API workflow, database integration, and batch processing without requiring OpenAI summarisation credits.

Audio transcription may still require OpenAI API access, depending on the configured audio-processing path.

## Database

The application uses SQLite to store meeting transcripts, summaries, and timestamps. By default, the database file is `talenthub.db` in the project directory.

The database location can be changed through `DATABASE_PATH`.

## Run Tests

Run the automated test suite:

```powershell
python -m pytest -q
```

Check Python syntax:

```powershell
python -m py_compile app.py
```

## Project Structure

```text
talenthub-meeting-summariser/
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
├── static/
│   ├── index.html
│   ├── script.js
│   └── style.css
└── tests/
```

The application may also create local files such as `.env` and `talenthub.db`. These should be handled according to the repository's `.gitignore` rules.

## Security Notes

- Never commit API keys or secrets to GitHub.
- Do not upload confidential recruitment transcripts without appropriate permission.
- Review AI-generated summaries for accuracy before relying on them.
- Avoid committing local database files, downloaded batch archives, or backup files unless the assignment specifically requires them.
