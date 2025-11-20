# Frontend UX & Flows (React)

Goal: A clear, friendly, and efficient UI that guides users through gathering information and drafting a will with chat + voice, document/image uploads, progress tracking, and export.

## Principles
- Chat-first, question-driven; surface the next best questions (minimize cognitive load).
- Upload-aware: drag/drop docs/images with immediate OCR summaries.
- Voice optional everywhere; smooth talk/listen controls and audio replies.
- Progress visible: gaps checklist and section milestones in a sidebar.
- Nimble contracts: treat backend payloads as JSON dicts; validate minimally at boundaries.
- Accessibility: keyboard-first, ARIA landmarks, readable defaults.

## Tech Stack
- React + Vite (SPA), React Router for lightweight routing (optional).
- State: Zustand or React Query + local component state (simple and nimble).
- Styling: Tailwind or CSS Modules; dark mode support.
- Realtime: WebSocket for chat + voice; optional SSE for activity logs.
- Audio: MediaRecorder (Opus/WebM) or PCM fallback; WebAudio for playback; browser SpeechSynthesis as fallback TTS.

## Main Views
- Onboarding
  - Collect jurisdiction, confirm disclaimers, start a session.
- Chat Workspace
  - Center: messages (user, assistant, tool outputs), inline attachments, transcription badges.
  - Left/Right Sidebar: progress (“Gaps”), info sections, quick facts chips.
  - Top bar: session selector, status, help.
  - Bottom: composer (text, upload, voice control).
- Upload Drawer
  - Drag/drop, file list, per-file OCR summary, link-to-session toggle.
- Review & Export
  - Draft preview (clauses and sections), accept/reject assumptions, export to DOCX/PDF.
- Settings
  - Voice device selection, TTS voice, accessibility preferences, data controls.

## Core Components
- AppShell (layout, theme, routing)
- ChatView
  - MessageList, MessageItem (roles: user/assistant/tool)
  - ChatComposer (textarea + send, upload button, push-to-talk)
  - AttachmentChip / UploadBadge
  - AssistantTyping (streaming deltas)
- VoiceBar
  - MicButton (push-to-talk/hold-to-talk), LevelMeter, Timer
  - AudioPlayer (tts playback, pause/resume)
- UploadPanel
  - Dropzone, FileItem (status: queued, processing, done, error)
  - OCRSummary (snippet preview), LinkToMessage toggle
- ProgressSidebar
  - SectionProgress (Jurisdiction, Family, Executors, Assets, Bequests, Trusts, Execution, Review)
  - GapList (BLOCKING first, then ADVISORY), NextQuestionCard
- DraftPreview
  - ClauseList, ClauseItem (edit note), ExportPanel
- Toasts/Modals (errors, confirmations)

## Key Flows
1) Start Session
- User lands on Onboarding → selects state/country, agrees to disclaimers → `POST /sessions`.
- Navigate to Chat Workspace with session_id; open WS `/chat/stream?session_id=...`.

2) Send Text Message
- User types → `POST /sessions/{id}/messages` or WS `user_message`.
- UI streams `assistant_delta` events; MessageItem updates live; on `state_update`, sidebar refreshes.

3) Upload Files/Images
- Drag/drop to UploadPanel → `POST /uploads` (multipart).
- Show per-file status; when preprocessing completes, display OCR summary and link to the latest message or create a system note message.
- If `mode=snapshots`, show a “multimodal used” badge.

4) Voice Input
- Press-to-talk → request mic permission; send `voice.start` over WS.
- Stream `voice.chunk` blobs (Opus/PCM) until release; send `voice.stop`.
- Backend returns interim transcript (`assistant_delta` with `transcript` tag) and then full assistant reply; if TTS enabled, stream `tts.chunk` for audio playback.

5) Resolve Gaps
- Sidebar lists gaps; user clicks a gap → autoscroll to assistant’s proposed question in Chat.
- Answer via chat or quick form; `state_update` removes/resolves the gap; sidebar updates.

6) Review & Export
- When READY_TO_DRAFT, open DraftPreview → render outline and clauses.
- Edit notes (local), accept assumptions, and click Export → `POST /drafts/{id}/export?format=docx|pdf` → download.

## WebSocket Events (contract sketch)
Outgoing
- `user_message` { text, attachments? }
- `voice.start` { format: "opus|pcm", sample_rate }
- `voice.chunk` { seq, bytes }
- `voice.stop` { }
- `ack` { received: event_id }

Incoming
- `assistant_delta` { text_delta?, transcript_delta?, message_id }
- `tool_call` { tool, args }
- `tool_result` { tool, result }
- `gap_update` { added[], resolved[] }
- `state_update` { profile?, draft_status?, questions? }
- `tts.chunk` { seq, bytes }
- `tts.end` { }
- `error` { code, message }

## Minimal Data Shapes (frontend)
- Message: { id, role: "user|assistant|tool", text, attachments?[] }
- Gap: { id, description, severity: "BLOCKING|ADVISORY" }
- Question: { id, text, rationale, gap_ids[] }
- UploadResult: { name, type, mode: "text|ocr|snapshots", biomarker_count, quality { score, reason } }

## Accessibility & Shortcuts
- Focus management: composer autofocus, landmark roles for chat list and sidebar.
- Keyboard: `Enter` send, `Shift+Enter` newline, `Cmd/Ctrl+K` toggle upload panel, `Space` push-to-talk (while composer focused).
- High contrast mode and reduced motion preference.

## Error Handling & Offline
- Connection lost banner; retry WS with backoff.
- Persist unsent composer text in localStorage per session.
- Show actionable error toasts (file too large, unsupported type, mic denied).

## Telemetry (minimal)
- Session duration, messages sent, uploads count, voice usage.
- Error counts per feature; anonymized only.

## Routing (optional)
- `/` → Onboarding
- `/s/:sessionId` → Chat Workspace
- `/s/:sessionId/review` → DraftPreview

## Next Steps
- Scaffold React app (Vite), add WS client, basic ChatView, and UploadPanel.
- Implement push-to-talk and TTS playback MVP.
- Integrate ProgressSidebar with `state_update` events.

