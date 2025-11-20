# AGENTS.md — Willit Project Conventions

Scope: This file governs the entire `willit/` directory tree.

Purpose: Encode succinct rules so future agents implement consistently. We favor nimble, function-first code over heavy frameworks.

## Design Principles (Nimble)
- Prefer plain JSON/dicts over heavy type systems. No Pydantic.
- Avoid classes unless absolutely necessary; use module-level async functions.
- Enums only when absolutely necessary (safety-critical state, strict external interop). Keep minimal, versioned, and transport as stable strings.
- Deterministic outputs: every prompt/tool returns text (No json_objects)
- Keep side-effects centralized in orchestrators; pure functions elsewhere.

## Directory & Module Layout
- `backend/willit/`
  - `router.py` – HTTP + WS/SSE routes. Accept/return raw JSON dicts.
  - `processing.py` – Orchestrates flows, state changes, tool calls.
  - `prompts.py` – Prompt builders and prompt-facing functions.
  - `prompt_drivers.py` – LLM/vision/ASR/TTS wrappers | ask_gpt_mcp_responses| ask_gpt_web_responses| ask_gpt_chat_completion_with_biomarkers| ask_gpt_chat_completion_no_biomarkers| ask_gpt_file_search_with_citation_modifier| ask_gpt_no_citation_modifier| ask_gpt_file_search| ask_gpt_content_prediction
  - `preprocessing.py` – Upload/image pipeline: MIME detect → OCR → parse → extract → embed.
  - `content_extraction.py` – Match learned-hand analyze style: HTML/JSON cleaning.
  - `will_logic_flow.py` – Mermaid diagrams + string constants describing guided flow.
  - `contracts.py` – Optional JSON Schemas + tiny runtime validators (no Pydantic).

Follow naming from learned-hand `platform/server/src/analyze`: no deep class hierarchies, descriptive function names, module-level constants for diagrams.

## Prompts & Output Contracts
- Build message histories as lists of `{role, content:[{type, text}]}` blocks.
- Place tasks/acceptance criteria in a developer/system message.
- Always require outputs inside:
  - ```json fenced blocks, or
  - Sentinel wrappers `~~| ... |~~` for simple lists.
- Include `version` and stable keys in outputs for future evolution.
- On parse failure: drivers retry with reduced prompt or schema enforcement.

## API & Events
- Router accepts/returns raw JSON dicts. Minimal runtime checks for required keys.
- WebSocket/SSE events: `assistant_delta`, `tool_call`, `tool_result`, `state_update`, `gap_update`, `voice.start|chunk|stop`, `tts.chunk|end`.
- Keep handlers thin; delegate logic to `processing.py`.

## Preprocessing
- Pipeline steps: MIME detect → page split → OCR (images/scanned PDFs) → layout parse → `content_extraction.extract_content` → embeddings (optional).
- Safety: size/time limits, MIME allowlist. Return concise summaries for UI linking.

## State & Storage
- Start simple (SQLite for dev), Postgres + object storage (MinIO) behind Docker later.
- Store file bytes in object storage; DB holds metadata and signed URLs.
- Version drafts; snapshot profile/gaps for each version.

## Observability
- Use structured logging with request/workflow IDs. Keep instrumentation optional and light.

## Security & Privacy
- Restrict MIME types. Consider basic virus-scan hook.
- Encrypt PII at rest; short-lived WS tokens; signed URLs.
- Redact in logs; never log raw uploads or secrets.

## Testing
- Favor shape validation and golden tests for prompt outputs.
- Unit tests for pure functions (`content_extraction`, parsers, `apply_fact_diff`).
- Contract tests for key endpoints and WS streaming where practical.

## Enums Policy (Important)
- Prefer plain strings for roles, states, severities.
- Introduce an enum only when:
  - It prevents unsafe state transitions, OR
  - It aligns with a strict external API/DB contract, OR
  - It materially simplifies validation in a critical path.
- Keep enum sets minimal; expose as strings at API boundaries; document versions.

## What to Avoid
- Heavy model typing (Pydantic) and over-specified schemas.
- Deep OOP hierarchies; singletons; global state besides controlled config.
- Hidden side-effects in prompt functions.

## References
- See `willit/docs/backend.md` for fuller design, flows, and prompt patterns.

