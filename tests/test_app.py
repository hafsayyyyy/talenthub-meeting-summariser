
import sqlite3

from fastapi.testclient import TestClient

import app


client = TestClient(app.app)


def test_home():
    response = client.get("/")

    assert response.status_code == 200


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_summarise_requires_transcript_or_audio():
    response = client.post("/summarise", data={})

    # FastAPI may return 400 or 422 for an empty request.
    assert response.status_code in (400, 422)


def test_summarise_saves_meeting(monkeypatch, tmp_path):
    # Use a temporary database so the real project database is untouched.
    test_db = str(tmp_path / "test_meetings.db")

    monkeypatch.setattr(app, "DATABASE_PATH", test_db)
    app.initialise_database()

    # Avoid calling the real OpenAI API.
    monkeypatch.setattr(
        app,
        "get_client",
        lambda: object(),
    )

    expected_summary = "- Ali will complete the design by Monday."

    monkeypatch.setattr(
        app,
        "generate_summary",
        lambda client, transcript: expected_summary,
    )

    transcript_text = (
        "The team discussed the project deadline. "
        "Ali will complete the design by Monday."
    )

    response = client.post(
        "/summarise",
        data={"transcript": transcript_text},
    )

    assert response.status_code == 200

    result = response.json()

    assert result["meeting_id"] == 1
    assert result["summary"] == expected_summary
    assert result["timestamp"]

    # Confirm the transcript and summary were stored in SQLite.
    with sqlite3.connect(test_db) as connection:
        row = connection.execute(
            "SELECT transcript, summary FROM meetings WHERE id = ?",
            (result["meeting_id"],),
        ).fetchone()

    assert row is not None
    assert row[0] == transcript_text
    assert row[1] == expected_summary
