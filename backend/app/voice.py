"""Voice pipeline (server-side, optional).

The frontend uses the browser's built-in Web Speech API by default (no keys,
works offline-ish), but a supervisor driving to site deserves a production
path: server-side speech-to-text and text-to-speech through any
OpenAI-compatible endpoint (OpenAI Whisper + TTS, or self-hosted equivalents).

Endpoints
---------
POST /api/voice/transcribe   multipart audio -> {"text": "..."}
POST /api/voice/speak        {"text": "..."}      -> audio/mpeg stream
"""
import logging

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel

from .config import settings

logger = logging.getLogger("precode.voice")
router = APIRouter(prefix="/api/voice", tags=["voice"])


def _client() -> OpenAI:
    if not settings.openai_api_key:
        raise HTTPException(
            503,
            "Server-side voice is not configured (OPENAI_API_KEY missing). "
            "The UI will use browser speech instead.",
        )
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.llm_base_url)


@router.post("/transcribe")
async def transcribe(audio: UploadFile):
    """Speech-to-text: accepts a webm/wav/mp3 recording, returns transcript."""
    client = _client()
    data = await audio.read()
    if not data:
        raise HTTPException(422, "empty audio upload")
    try:
        result = client.audio.transcriptions.create(
            model=settings.stt_model,
            file=(audio.filename or "speech.webm", data, audio.content_type or "audio/webm"),
        )
        return {"text": result.text}
    except Exception as exc:
        logger.exception("STT failed")
        raise HTTPException(502, f"transcription failed: {exc}") from exc


class SpeakBody(BaseModel):
    text: str


@router.post("/speak")
def speak(body: SpeakBody):
    """Text-to-speech: returns an MP3 stream of the answer."""
    text = body.text.strip()
    if not text:
        raise HTTPException(422, "text required")
    client = _client()
    try:
        audio = client.audio.speech.create(
            model=settings.tts_model, voice=settings.tts_voice, input=text[:4000]
        )
        return StreamingResponse(
            audio.iter_bytes(), media_type="audio/mpeg",
            headers={"Content-Disposition": "inline; filename=answer.mp3"},
        )
    except Exception as exc:
        logger.exception("TTS failed")
        raise HTTPException(502, f"speech synthesis failed: {exc}") from exc
