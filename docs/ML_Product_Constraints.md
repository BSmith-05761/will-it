# ML Product Constraints (Voice + Multimodal Chat)

Purpose: Define strict product constraints for the end‑to‑end agent experience: audio input/output, multimodal uploads, always‑streaming responses, and the Draft & Refine workflow. These rules guide UX, backend orchestration (chat_router), and prompt contracts. Nimble first: plain JSON, minimal validation, enums only when necessary.

## Core Experience (Non‑negotiable)
- Always streaming output by default.
  - Text stream: incremental `assistant_delta` events.
  - Audio stream: optional; when enabled, TTS chunks (`tts.chunk`) are emitted in parallel with text deltas.
- User input modes:
  - Text: always available.
  - Voice: press/hold‑to‑talk; audio chunks streamed (`voice.start|chunk|stop`).
  - Drag & drop files: images (objects/photos/screenshots), scanned docs, PDFs, DOCX, TXT.
- Outputs:
  - Conversation text (chat messages) and optional synchronized audio.
  - Draft pane: when “Draft & Refine” is pressed (or status READY_TO_DRAFT), show live, editable WILL at the right of chat.

## Chat Router (chat_router) Method
- Orchestrator responsibilities (deterministic, minimal state):
  - Accept `user_message`, optional `attachments`, and current session state (profile/gaps/draft status).
  - Call preprocessing for attachments → biomarked text; emit `tool_result` summary.
  - Run prompt functions in order: `extract_facts_from_text` → merge → `list_gaps` → `propose_next_questions` OR `generate_draft_outline`/`suggest_clause` if READY_TO_DRAFT.
  - Stream assistant content immediately; never buffer full responses before streaming.
  - If audio mode is ON, concurrently synthesize TTS and stream `tts.chunk`.
  - Emit `gap_update` and `state_update` as profile/draft changes occur.
- Tooling fan‑out (examples): `extract_from_image`, `summarize_upload`, `embed_and_index` (optional), `validate_jurisdiction`, `export_docx/pdf`.
- Draft gate: do not enter drafting until BLOCKING gaps are resolved. `READY_TO_DRAFT` unlocks the Draft & Refine pane.

## Streaming Contracts
- Incoming (from client)
  - `user_message` { text, attachments? }
  - `voice.start` { format: "opus|pcm", sample_rate }
  - `voice.chunk` { seq, bytes }
  - `voice.stop` { }
  - `toggle.audio` { enabled: true|false }
- Outgoing (to client)
  - `assistant_delta` { text_delta?, transcript_delta?, message_id }
  - `tool_call` { tool, args }
  - `tool_result` { tool, result }
  - `gap_update` { added[], resolved[] }
  - `state_update` { profile?, draft_status?, questions? }
  - `tts.chunk` { seq, bytes }, `tts.end` { }
  - `error` { code, message }

## File Intake Constraints
- Accepted types (preference order): TXT, DOCX, PDF, images (PNG/JPG/JPEG/TIFF), screenshots.
- Size guidance (soft caps; reject with clear error beyond hard limits):
  - Images: ≤ 10 MB each; PDFs: ≤ 25 MB; DOCX/TXT: ≤ 10 MB. Batches ≤ 100 MB total.
- Preprocessing behavior (see preprocessing.md):
  - Prefer native text (TXT/DOCX). PDFs: try text → OCR if low quality → snapshots if still poor.
  - Biomarkers appended at `\n\n` segment ends: `【mrkr||<document_name>||d-<hex>】`.
  - Wrapped doc blocks: `Start of document, <name|type>` … `End of document`.
- Multimodal fallback:
  - If extraction poor, attach page snapshots; prompt functions may call a vision model branch.

## Voice I/O Constraints
- Input: browser mic (MediaRecorder Opus/WebM preferred; PCM fallback). Stream chunks within 100–250ms.
- STT: server ASR (e.g., Whisper/faster‑whisper) or client STT fallback. Interim transcripts can be sent as `assistant_delta.transcript_delta`.
- Output: TTS streaming (server or browser SpeechSynthesis). If server TTS fails, fallback to text‑only.
- Latency targets: first text token < 400ms after receiving user message; first audio chunk < 800ms.

## Draft & Refine Workflow
- Entry: user presses “Draft & Refine” or router emits `status: READY_TO_DRAFT` with questions empty.
- UI: right‑side editable pane shows draft outline and clauses; changes are local until user clicks “Apply Changes”.
- Backend: accepts partial edits; records a new draft version and re‑validates clauses (`validate_jurisdiction`, `validate_execution_requirements`).
- Streaming while drafting: continue to stream reasoning or status updates (e.g., “Drafting Executors clause…”) as `assistant_delta` and `state_update` with section progress.
- Export: `POST /drafts/:id/export?format=docx|pdf` returns file; export is based on the latest accepted version.

## Safety & Compliance Constraints
- Disclaimers: always show “not legal advice”; require explicit acceptance at onboarding.
- Jurisdictional gating: do not enable e‑will/remote witnessing flows where not permitted; block on state capability.
- Privacy: minimize PII; do not store secrets (digital keys/passwords). Redact in logs; short‑lived tokens for WS.
- UPL boundaries (product copy/UX): explain options neutrally; route complex scenarios to attorney review.

## Failure Modes & Fallbacks
- ASR unavailable → accept text input; show banner that voice is offline.
- TTS unavailable → continue with text stream only.
- OCR/vision unavailable → store files; invite user to answer manually; mark gaps accordingly.
- WS drops → reconnect with backoff; fall back to HTTP polling if necessary (optional).

## Resource & Token Constraints
- Context window: keep rolling summary of resolved facts; include only recent history and linked biomarked snippets.
- Truncation: apply token budgeting; prefer structured outputs; no giant raw dumps.

## Acceptance Criteria (Go/No‑Go)
- Streaming defaults to ON; toggling audio affects only TTS, not text stream.
- Text input always available while voice is recording (no modal lockout).
- Drag‑and‑drop uploads work from desktop and mobile (where supported).
- Preprocessing returns a single aggregated biomarked text and per‑doc metadata.
- Router does not draft until BLOCKING gaps are resolved.
- Draft pane appears and remains editable; exports succeed as DOCX/PDF.
- Failures degrade gracefully with clear user messaging; chat remains usable.

See also: backend.md, frontend_ux.md, preprocessing.md, business_logic_phases.md, legal_requirements_us.md.
