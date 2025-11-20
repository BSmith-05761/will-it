import os
import sys
import logging
from pathlib import Path
from uuid import uuid4
from typing import List
from datetime import datetime

from fastapi import FastAPI, APIRouter, File, UploadFile, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse

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
from willit.chat_router import handle_user_message
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

    def _ensure_session_dir(session_id: str) -> Path:
        path = UPLOAD_ROOT / session_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    @api.post("/uploads")
    async def upload(session_id: str | None = None, files: List[UploadFile] = File(...)):
        sid = session_id or "default"
        session_dir = _ensure_session_dir(sid)
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
        docs = []
        for uf in files:
            blob = await uf.read()
            safe_name = uf.filename or f"file-{uuid4().hex}"
            raw_path = session_dir / f"{timestamp}-{safe_name}"
            try:
                raw_path.write_bytes(blob)
            except Exception:
                logging.exception("Failed to persist raw upload %s", raw_path)
            docs.append({"filename": safe_name, "blob": blob})
        result = preprocess_documents(docs)
        try:
            processed_path = session_dir / f"preprocessed-{timestamp}.txt"
            processed_path.write_text(result.get("text", ""), encoding="utf-8")
        except Exception:
            logging.exception("Failed to persist preprocessed text for session %s", sid)
        return JSONResponse(result)

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
