
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from openai import OpenAI
from pydantic import BaseModel, Field

load_dotenv()

app = FastAPI(
    title="TalentHub Meeting Summariser API",
    description="API for summarising meeting transcripts.",
    version="1.0.0",
)


class SummaryRequest(BaseModel):
    transcript: str = Field(
        ...,
        min_length=1,
        description="The meeting transcript to summarise.",
    )


class SummaryResponse(BaseModel):
    summary: str


@app.get("/")
def home():
    return {
        "message": "TalentHub Meeting Summariser API is running",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/summarize", response_model=SummaryResponse)
def summarize_meeting(request: SummaryRequest):
    transcript = request.transcript.strip()

    if not transcript:
        raise HTTPException(
            status_code=422,
            detail="Transcript cannot be empty.",
        )

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="OpenAI API key is not configured.",
        )

    try:
        client = OpenAI(api_key=api_key)

        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Summarize meeting transcripts clearly. "
                        "Include key discussion points, decisions, "
                        "and action items when available. "
                        "Do not invent information."
                    ),
                },
                {
                    "role": "user",
                    "content": transcript,
                },
            ],
            temperature=0.3,
        )

        summary = response.choices[0].message.content

        if not summary:
            raise HTTPException(
                status_code=502,
                detail="The summarization service returned no summary.",
            )

        return SummaryResponse(summary=summary.strip())

    except HTTPException:
        raise
    except Exception:
        app.logger.exception("Meeting summarization failed.")
        raise HTTPException(
            status_code=502,
            detail="Unable to summarize the meeting at this time.",
        )
