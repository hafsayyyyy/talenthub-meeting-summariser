
import pytest
from fastapi.testclient import TestClient

import app


client = TestClient(app.app)


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_home():
    response = client.get("/")

    assert response.status_code == 200


def test_summarise_requires_input():
    response = client.post("/summarise", data={})

    assert response.status_code == 422


def test_summarise_saves_meeting(monkeypatch, tmp_path):
    # Use a temporary database for this test.
    test_db = str(tmp_path / "test_meetings.db")

    monkeypatch.setattr(app, "DATABASE_PATH", test_db)
    app.initialise_database()

    # Disable demo mode for this test.
    # The mocked function below means no OpenAI API call is made.
    monkeypatch.setenv("DEMO_MODE", "false")

    # Mock the OpenAI client.
    monkeypatch.setattr(
        app,
        "get_client",
        lambda: object(),
    )

    expected_summary = "- Ali will complete the design by Monday."

    # Mock AI summary generation.
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

    # Confirm the meeting was stored in SQLite.
    with app.get_connection() as connection:
        saved_meeting = connection.execute(
            "SELECT transcript, summary FROM meetings WHERE id = ?",
            (result["meeting_id"],),
        ).fetchone()

    assert saved_meeting is not None
    assert saved_meeting["transcript"] == transcript_text
    assert saved_meeting["summary"] == expected_summary
