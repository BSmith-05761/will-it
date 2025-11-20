from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, Callable, List
from pathlib import Path
import logging
import json
from datetime import datetime

from .prompt_drivers import stream_gpt_web_responses

logger = logging.getLogger("willit.chat")
UPLOAD_ROOT = Path(__file__).resolve().parents[2] / "uploads"
UPLOAD_ROOT.mkdir(exist_ok=True)


def _load_business_logic_text() -> str:
    """Load the business logic phases doc from common locations.

    Search order:
      1) WILLIT_DOCS_DIR env
      2) /app/docs (Docker image)
      3) <repo-root>/docs (local dev)
    """
    candidates: list[Path] = []
    env_dir = os.getenv("WILLIT_DOCS_DIR")
    if env_dir:
        candidates.append(Path(env_dir) / "business_logic_phases.md")
    candidates.append(Path("/app/docs/business_logic_phases.md"))
    # repo root: ../../ from this file -> will-it/
    repo_root = Path(__file__).resolve().parents[2]
    candidates.append(repo_root / "docs" / "business_logic_phases.md")

    for p in candidates:
        try:
            if p.is_file():
                return p.read_text(encoding="utf-8")
        except Exception:
            continue

    # Minimal fallback text (avoid noisy error strings in the stream)
    return (
        "Willit planning phases: eligibility, jurisdiction, family, fiduciaries, assets,"
        " designations, bequests, trusts, taxes/debts, protections, admin powers,"
        " execution, review/export, and post‑execution follow‑ups."
    )


async def _fallback_stream(ws_send_json: Callable[[dict], Any], session_id: str = "default"):
    # Stream a short header then the first N paragraphs from the phases doc
    preface = (
        "I’m Willit. Let’s gather what we need to draft your will.\n"
        "Here’s the plan we’ll follow (high‑level):\n\n"
    )
    logger.info(f"[{session_id}] Using local placeholder response (no network)")
    full_text = ""
    full_text += preface
    await ws_send_json({"type": "assistant_delta", "text_delta": preface, "full_text": full_text})
    await asyncio.sleep(0)
    doc = _load_business_logic_text()
    parts = [p.strip() for p in doc.replace("\r\n", "\n").split("\n\n") if p.strip()]
    max_parts = 2
    for para in parts[:max_parts]:
        chunk = para + "\n\n"
        full_text += chunk
        await ws_send_json({"type": "assistant_delta", "text_delta": chunk, "full_text": full_text})
        await asyncio.sleep(0)
    if len(parts) > max_parts:
        chunk = "…(truncated)\n"
        full_text += chunk
        await ws_send_json({"type": "assistant_delta", "text_delta": chunk, "full_text": full_text})


# In-memory conversation history per session_id
_HISTORY: dict[str, List[dict]] = {}


def _persist_history(session_id: str):
    try:
        history = _HISTORY.get(session_id, [])
        path = UPLOAD_ROOT / session_id
        path.mkdir(parents=True, exist_ok=True)
        (path / "message_history.json").write_text(
            json.dumps(history, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.exception("Failed to persist history for %s: %s", session_id, exc)


def _create_event_recorder(session_id: str) -> Callable[[dict], None]:
    path = UPLOAD_ROOT / session_id
    path.mkdir(parents=True, exist_ok=True)
    log_file = path / "responses_events.log"

    def _record(event: dict):
        try:
            payload = {"ts": datetime.utcnow().isoformat(), **event}
            with log_file.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.debug("Failed to record stream event for %s: %s", session_id, exc)

    return _record


def _get_history(session_id: str) -> List[dict]:
    """Return message history for session. Seed with developer doc if new."""
    if session_id not in _HISTORY:
        doc = _load_business_logic_text()
        _HISTORY[session_id] = [
            {
                "role": "developer",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "You are a will‑prep assistant. Use the following plan as your system context.\n\n"
                            + doc
                        ),
                    }
                ],
            }
        ]
    return _HISTORY[session_id]


async def handle_user_message(ws_send_json, message: Dict[str, Any], session_id: str = "default"):
    """Basic chat router with persistent context per session.

    ws_send_json: callable(dict) -> awaitable, typically WebSocket.send_json
    message: incoming event with keys { type: 'user_message', text, attachments? }
    session_id: conversation key to persist history; 'default' if not provided
    """
    text = (message or {}).get("text") or ""
    mode = ((message or {}).get("mode") or "research").lower()
    logger.info(f"[{session_id}] user: {text} (mode={mode})")
    await ws_send_json({"type": "ack", "received": "user_message"})
    # Append user message
    history = _get_history(session_id)
    history.append({"role": "user", "content": [{"type": "input_text", "text": text}]})

    network_enabled = os.getenv("WILLIT_ALLOW_NETWORK", "false").lower() == "true"

    try:
        if network_enabled:
            message_history = list(history)
            final = ""
            reasoning_buffers: dict[str, str] = {"reasoning": "", "summary": ""}
            reasoning_seen = False
            event_recorder = _create_event_recorder(session_id)
            enable_web = mode != "fast"
            effort = "low" if mode == "fast" else "medium"

            loop = asyncio.get_running_loop()

            def on_delta(delta: str):
                nonlocal final
                final += delta
                current_full_text = final
                loop.call_soon_threadsafe(
                    lambda text_delta=delta, full_text=current_full_text: asyncio.create_task(
                        ws_send_json(
                            {
                                "type": "assistant_delta",
                                "text_delta": text_delta,
                                "full_text": full_text,
                            }
                        )
                    )
                )

            def on_reasoning_delta(delta: str, variant: str):
                if not delta:
                    return
                nonlocal reasoning_seen
                reasoning_seen = True
                logger.debug("Reasoning delta (%s): %s", variant, delta[:200])
                total = reasoning_buffers.get(variant, "") + delta
                reasoning_buffers[variant] = total
                loop.call_soon_threadsafe(
                    lambda text_delta=delta, full_text=total, kind=variant: asyncio.create_task(
                        ws_send_json(
                            {
                                "type": "assistant_reasoning_delta",
                                "variant": kind,
                                "text_delta": text_delta,
                                "full_text": full_text,
                            }
                        )
                    )
                )

            def on_tool_event(event_type: str, payload: dict):
                logger.info("Tool event [%s]: %s", event_type, payload)
                loop.call_soon_threadsafe(
                    lambda evt=event_type, data=payload: asyncio.create_task(
                        ws_send_json(
                            {
                                "type": "tool_event",
                                "event_type": evt,
                                "details": data,
                            }
                        )
                    )
                )

            try:
                logger.info(f"[{session_id}] Awaiting response from model…")
                await loop.run_in_executor(
                    None,
                    lambda: stream_gpt_web_responses(
                        input_prompt=message_history,
                        model_name=os.getenv("WILLIT_MODEL", "gpt-5.1"),
                        effort=effort,
                        verbosity="medium",
                        on_delta=on_delta,
                        on_reasoning_delta=on_reasoning_delta,
                        on_tool_event=on_tool_event,
                        event_recorder=event_recorder,
                        enable_web_search=enable_web,
                        max_tool_calls=int(os.getenv("WILLIT_MAX_TOOL_CALLS", "3")),
                    ),
                )
                if reasoning_seen:
                    await ws_send_json({"type": "assistant_reasoning_done"})
                history.append({"role": "assistant", "content": [{"type": "output_text", "text": final}]})
                logger.info(f"[{session_id}] assistant: {final}")
            except Exception as e:
                await ws_send_json({"type": "error", "code": "stream_failed", "message": str(e)})
                logger.exception(f"[{session_id}] model stream failed: {e}")
                if reasoning_seen:
                    await ws_send_json({"type": "assistant_reasoning_done"})
                await _fallback_stream(ws_send_json, session_id)
        else:
            await _fallback_stream(ws_send_json, session_id)
    finally:
        _persist_history(session_id)
