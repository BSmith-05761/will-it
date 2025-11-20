from __future__ import annotations

import io
import os
from typing import Optional, Callable

from .prompt_drivers import sync_client


def _stt_model() -> str:
    return os.getenv("WILLIT_STT_MODEL", "gpt-4o-mini-transcribe")


def _tts_model() -> str:
    return os.getenv("WILLIT_TTS_MODEL", "gpt-4o-mini-tts")


def _tts_voice() -> str:
    return os.getenv("WILLIT_TTS_VOICE", "alloy")


def _tts_speed() -> float:
    try:
        return float(os.getenv("WILLIT_TTS_SPEED", "1.8"))
    except ValueError:
        return 4.0


def transcribe_audio(file_bytes: bytes, content_type: str | None = None) -> str:
    """Convert raw audio bytes to text using OpenAI STT."""
    if not file_bytes:
        return ""
    ct = content_type or "audio/webm"
    response = sync_client.audio.transcriptions.create(
        model=_stt_model(),
        file=("input", io.BytesIO(file_bytes), ct),
    )
    return (getattr(response, "text", "") or "").strip()


def _chunk_text(text: str, max_chars: int = 3500, min_chars: int = 600) -> list[str]:
    """Split text into chunks preferring newline boundaries, then spaces, preserving all chars."""
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    total_len = len(text)

    while start < total_len:
        # optimistic end for this chunk
        end = min(start + max_chars, total_len)

        # if we're at the tail already, capture remainder
        if end >= total_len:
            chunks.append(text[start:total_len])
            break

        # only consider splits once we've accumulated min_chars
        search_floor = min(start + min_chars, end)

        split_pos = text.rfind("\n", search_floor, end)
        if split_pos != -1:
            split_pos += 1  # include newline with the current chunk
        else:
            space_pos = text.rfind(" ", search_floor, end)
            if space_pos != -1:
                split_pos = space_pos + 1  # include trailing space

        if split_pos is None or split_pos <= start:
            split_pos = end  # fallback: hard cut at max window

        chunks.append(text[start:split_pos])
        start = split_pos

    return chunks


def _speech_response_to_bytes(response) -> Optional[bytes]:
    audio_bytes = getattr(response, "content", None)
    if audio_bytes:
        return audio_bytes
    data = getattr(response, "data", None)
    if isinstance(data, bytes):
        return data
    if isinstance(data, list):
        chunks: list[bytes] = []
        for chunk in data:
            if isinstance(chunk, dict):
                audio_chunk = chunk.get("audio")
                if isinstance(audio_chunk, bytes):
                    chunks.append(audio_chunk)
        if chunks:
            return b"".join(chunks)
    return None


def generate_speech(text: str) -> Optional[bytes]:
    """Generate speech audio bytes for the supplied text."""
    if not text:
        return None
    max_chars = int(os.getenv("WILLIT_TTS_MAX_CHARS", "3500"))
    chunks = _chunk_text(text, max_chars=max_chars)
    audio_segments: list[bytes] = []
    for chunk in chunks:
        response = sync_client.audio.speech.create(
            model=_tts_model(),
            voice=_tts_voice(),
            speed=_tts_speed(),
            input=chunk,
        )
        bytes_part = _speech_response_to_bytes(response)
        if bytes_part:
            audio_segments.append(bytes_part)
    if not audio_segments:
        return None
    if len(audio_segments) == 1:
        return audio_segments[0]
    return b"".join(audio_segments)
