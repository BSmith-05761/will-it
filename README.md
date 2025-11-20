# Willit — Dev Setup

Docker Compose brings up the backend (FastAPI) and a minimal frontend (React/Vite). The backend includes the preprocessing pipeline with biomarker generation and optional OCR.

## Prereqs
- Docker and Docker Compose

## Run

```bash
cd willit
docker compose up --build
```

Backend: http://localhost:8000/api/health

Frontend: http://localhost:5173

## Local run (no Docker)

- Install deps:
  - cd will-it
  - pip install -r backend/requirements.txt
- Start backend:
  - python backend/main.py
  - I added a path fix and a uvicorn runner; server listens on http://localhost:8000
- Verify:
  - curl http://localhost:8000/api/health
- Start frontend (optional):
  - cd will-it/frontend
  - npm install
  - npm run dev
  - Open http://localhost:5173
- Test chat: type a message; you’ll see streaming text from the business logic doc.
- Test uploads: attach TXT/DOCX/PDF/PNG/JPG; you’ll see “Upload processed: … (mode)”

## Notes
- OCR and PDF rasterization rely on Tesseract and Poppler; the backend Dockerfile installs these. Python libs are optional and the code degrades gracefully if missing.
- Endpoints are nimble (plain JSON). No Pydantic models are required.
- Uploads: POST /api/uploads (multipart, key "files"). Returns biomarked text blocks and per-file metadata.
- WebSocket: /chat/stream (stub echo of messages). Frontend demonstrates a simple chat and upload flow.
- Default model: `gpt-5` for reasoning streams. Override with `WILLIT_MODEL` if needed, but keep a reasoning-capable Responses model to preserve tool + reasoning deltas.

### Chat streaming and prompt drivers
- The WebSocket streams assistant deltas using a placeholder that reads docs/business_logic_phases.md.
- If you already have a top-level `prompt_drivers` module (e.g., `Courses/common/prompt_drivers.py`) and want to use it to call an actual model, start the backend with `WILLIT_ALLOW_NETWORK=true` and ensure the module is on `PYTHONPATH`. The router will then call `stream_gpt_web_responses(...)` with the phases doc as developer context and stream real deltas.

## Directory
- backend/ — FastAPI app (main.py) and willit/ package with preprocessing.
- frontend/ — Vite React skeleton (chat + upload demo).
- docker/ — Dockerfiles for backend and frontend.
- docs/ — Architecture, backend prompts, preprocessing, business logic, legal requirements.
