import os
import sys
import json
import logging
import base64
from pathlib import Path
from uuid import uuid4
from typing import List
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, APIRouter, File, UploadFile, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

"""Ensure project root (will-it) is on sys.path so `prompt_drivers` is importable.
This is necessary when running `python backend/main.py` locally.
"""
ROOT = Path(__file__).resolve().parent.parent  # will-it/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

UPLOAD_ROOT = ROOT / "uploads"
UPLOAD_ROOT.mkdir(exist_ok=True)

# Load .env when present (local runs)
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(dotenv_path=ROOT / ".env")
except Exception:
    pass

from willit.preprocessing import preprocess_documents
from willit.chat_router import (
    handle_user_message,
    append_upload_context,
    append_upload_image,
    register_session_storage_dir,
)
from willit.voice import transcribe_audio, generate_speech
from fastapi.middleware.cors import CORSMiddleware


def create_app() -> FastAPI:
    # Basic logging config for local runs (uvicorn sets its own when used as ASGI server)
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    app = FastAPI(title="Willit Backend", version=os.getenv("WILLIT_VERSION", "0.1.0"))
    # Dev CORS (open); tighten in production
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api = APIRouter(prefix="/api")

    # In-memory session store (dev only)
    sessions: dict[str, dict] = {}

    @api.get("/health")
    async def health():
        return {"status": "ok"}

    @api.post("/sessions")
    async def create_session(body: dict | None = None):
        sid = str(uuid4())
        sessions[sid] = {
            "id": sid,
            "jurisdiction": (body or {}).get("jurisdiction"),
            "status": "active",
        }
        return sessions[sid]

    @api.get("/sessions/{session_id}")
    async def get_session(session_id: str):
        s = sessions.get(session_id)
        if not s:
            raise HTTPException(status_code=404, detail="session not found")
        return s

    def _sanitize_name(name: str) -> str:
        allowed = "-_."
        cleaned = "".join(ch if ch.isalnum() or ch in allowed else "_" for ch in name.strip())
        return cleaned or f"file-{uuid4().hex}"

    @api.post("/uploads")
    async def upload(session_id: str | None = None, files: List[UploadFile] = File(...)):
        sid = session_id or "default"
        now = datetime.now(ZoneInfo("America/New_York"))
        display_stamp = now.strftime("%m/%d/%H/%M")
        folder_stamp = display_stamp.replace("/", "-")
        run_dir = UPLOAD_ROOT / folder_stamp
        suffix = 1
        while run_dir.exists():
            run_dir = UPLOAD_ROOT / f"{folder_stamp}-{suffix}"
            suffix += 1
        run_dir.mkdir(parents=True, exist_ok=True)
        register_session_storage_dir(sid, run_dir)
        docs = []
        stored_files = []
        for uf in files:
            blob = await uf.read()
            safe_name = uf.filename or f"file-{uuid4().hex}"
            cleaned = _sanitize_name(safe_name)
            raw_filename = f"processed_file_{cleaned}"
            raw_path = run_dir / raw_filename
            try:
                raw_path.write_bytes(blob)
            except Exception:
                logging.exception("Failed to persist raw upload %s", raw_path)
            stored_files.append(
                {
                    "original_name": safe_name,
                    "stored_name": raw_filename,
                    "bytes": len(blob),
                }
            )
            docs.append({"filename": safe_name, "blob": blob})
        result = preprocess_documents(docs)
        evidence_records = []
        try:
            documents = result.get("documents") or []
            for idx, doc in enumerate(documents, start=1):
                doc_name = doc.get("name") or doc.get("filename") or f"document-{idx}"
                cleaned_doc = _sanitize_name(doc_name)
                processed_text = doc.get("text_block") or ""
                if processed_text:
                    evidence_filename = f"Processed_evidance_{cleaned_doc}.txt"
                    evidence_path = run_dir / evidence_filename
                    evidence_path.write_text(processed_text, encoding="utf-8")
                    evidence_records.append(
                        {
                            "document_name": doc_name,
                            "stored_name": evidence_filename,
                            "biomarker_count": doc.get("biomarker_count"),
                            "mode": doc.get("mode"),
                        }
                    )
                    try:
                        append_upload_context(sid, doc_name, processed_text)
                    except Exception:
                        logging.exception("Failed to append upload context for %s", doc_name)
                image_b64 = doc.get("image_base64")
                if image_b64:
                    try:
                        append_upload_image(sid, doc_name, image_b64, doc.get("mime_type"))
                    except Exception:
                        logging.exception("Failed to append uploaded image for %s", doc_name)
        except Exception:
            logging.exception("Failed to persist processed evidence for upload folder %s", run_dir.name)
        metadata = {
            "session_id": sid,
            "timestamp_label": display_stamp,
            "timestamp_iso": now.isoformat(),
            "run_directory": run_dir.name,
            "file_count": len(stored_files),
            "settings": {
                "model": os.getenv("WILLIT_MODEL", "gpt-5.1"),
                "allow_network": os.getenv("WILLIT_ALLOW_NETWORK", "false"),
            },
            "files": stored_files,
            "evidence": evidence_records,
        }
        try:
            (run_dir / "metadata.json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            logging.exception("Failed to write metadata for upload folder %s", run_dir.name)
        return JSONResponse(result)

    @api.post("/voice-query")
    async def voice_query(audio: UploadFile = File(...)):
        if audio is None:
            raise HTTPException(status_code=400, detail="audio file required")
        blob = await audio.read()
        if not blob:
            raise HTTPException(status_code=400, detail="empty audio payload")
        try:
            transcript = transcribe_audio(blob, audio.content_type or audio.headers.get("content-type"))
        except Exception as exc:
            logging.exception("voice transcription failed: %s", exc)
            raise HTTPException(status_code=500, detail="transcription_failed") from exc
        if not transcript:
            raise HTTPException(status_code=400, detail="unable to transcribe audio")
        return {
            "transcript": transcript,
        }

    class TTSRequest(BaseModel):
        text: str

    @api.post("/tts")
    async def tts_endpoint(payload: TTSRequest):
        if not payload.text.strip():
            raise HTTPException(status_code=400, detail="text required")
        try:
            audio_bytes = generate_speech(payload.text.strip())
        except Exception as exc:
            logging.exception("tts failed: %s", exc)
            raise HTTPException(status_code=500, detail="tts_failed") from exc
        if not audio_bytes:
            raise HTTPException(status_code=500, detail="tts_empty_audio")
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        return {"audio_base64": audio_b64}

    @app.websocket("/chat/stream")
    async def chat_stream(ws: WebSocket):
        await ws.accept()
        try:
            while True:
                data = await ws.receive_json()
                if data.get("type") == "user_message":
                    # Use session_id from query params if provided, else 'default'
                    session_id = ws.query_params.get("session_id", "default")
                    await handle_user_message(ws.send_json, data, session_id)
                elif data.get("type") == "voice.start":
                    await ws.send_json({"type": "ack", "received": "voice.start"})
                elif data.get("type") == "voice.stop":
                    await ws.send_json({"type": "ack", "received": "voice.stop"})
        except WebSocketDisconnect:
            pass

    app.include_router(api)
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
