"""
Project-level prompt drivers for Will‑It.

This restores the async drivers (AsyncOpenAI) you specified and also includes a
sync streaming driver used by the chat UI scaffold.

Exports:
- auth_instructions, citation_requirements
- ask_gpt_mcp_responses (async)
- ask_gpt_web_responses (async)
- ask_gpt_chat_completion_with_biomarkers (async)
- ask_gpt_chat_completion_no_biomarkers (async)
- ask_gpt_file_search_with_citation_modifier (async)
- ask_gpt_no_citation_modifier (async)
- ask_gpt_file_search (async)
- ask_gpt_content_prediction (async)
- stream_gpt_web_responses (sync streaming via Responses API)
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional, Callable, List, Any
from functools import wraps
from openai import AsyncOpenAI, OpenAI

logger = logging.getLogger(__name__)

# Clients
async_client = AsyncOpenAI()
sync_client = OpenAI()


def _has_responses_api() -> bool:
    try:
        return hasattr(sync_client, "responses") and hasattr(async_client, "responses")
    except Exception:
        return False


def _flatten_messages(input_prompt: List[dict]) -> List[dict]:
    """Convert Responses-style message contents into Chat Completions messages.

    Maps "developer" -> "system" and concatenates content blocks' text fields.
    """
    out: List[dict] = []
    for m in input_prompt or []:
        role = m.get("role", "user")
        if role == "developer":
            role = "system"
        blocks = m.get("content") or []
        texts: List[str] = []
        for b in blocks:
            if not isinstance(b, dict):
                continue
            # accept keys: text, input_text, output_text
            t = b.get("text") or b.get("input_text") or b.get("output_text")
            if isinstance(t, str):
                texts.append(t)
        content = "\n\n".join(texts) if texts else ""
        out.append({"role": role, "content": content})
    return out


class _CompatResponse:
    """Simple wrapper to emulate Responses API's output_text from a chat completion."""

    def __init__(self, completion):
        self._completion = completion
        try:
            self.output_text = completion.choices[0].message.content or ""
        except Exception:
            self.output_text = ""

    @property
    def choices(self):
        return getattr(self._completion, "choices", [])


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

auth_instructions = (
    "You are authorized to operate tools on behalf of the user within policy."
    " Use only approved tools and redact sensitive data in outputs."
)

citation_requirements = (
    "Provide citations when you rely on external sources. Prefer primary law."
    " Use Bluebook format where applicable."
)


# ---------------------------------------------------------------------------
# Async drivers (AsyncOpenAI)
# ---------------------------------------------------------------------------


async def ask_gpt_mcp_responses(
    *,
    input_prompt: list[dict],
    model_name: str = "gpt-5",
    effort: str = "low",
    verbosity: str = "medium",
    max_tool_calls: int = 35,
    vs_id: str | None = None,
):
    """Responses API with MCP tool configured via env (async)."""
    tools: list[dict] = []
    if vs_id and os.getenv("MCP_SERVER_URL") and os.getenv("MCP_AUTHORIZATION_KEY"):
        logger.info("Spinning up MCP tool for case law retrieval")
        tools.append(
            {
                "type": "mcp",
                "server_label": "relevant_legal_references",
                "server_description": (
                    "Use Search to verify and answer the question—do not rely on assumptions or prior training. "
                    "Use Fetch to retrieve the relevant source materials. Incorporate the fetched information into your "
                    "answer and cite it using the Biomarker method."
                ),
                "server_url": os.getenv("MCP_SERVER_URL"),
                "require_approval": "never",
                "headers": {
                    "authorization": os.getenv("MCP_AUTHORIZATION_KEY"),
                    "vector-store-id": vs_id,
                },
            }
        )

    if _has_responses_api():
        response = await async_client.responses.create(
            model=model_name,
            input=input_prompt,
            reasoning={"effort": effort},
            text={"verbosity": verbosity},
            max_tool_calls=max_tool_calls,
            tools=tools,
            store=True,
            background=False,
        )
        return response
    # Fallback: chat completion (no tools)
    completion = await async_client.chat.completions.create(
        model=model_name,
        messages=_flatten_messages(input_prompt),
    )
    return _CompatResponse(completion)


async def ask_gpt_web_responses(
    *,
    input_prompt: list[dict],
    model_name: str = "gpt-5",
    effort: str = "medium",
    verbosity: str = "high",
):
    """Responses API with web_search_preview (async)."""
    if _has_responses_api():
        response = await async_client.responses.create(
            model=model_name,
            input=input_prompt,
            reasoning={"effort": effort},
            text={"verbosity": verbosity},
            tools=[
                {
                    "type": "web_search_preview",
                    "user_location": {"type": "approximate"},
                    "search_context_size": "medium",
                }
            ],
            store=True,
        )
        return response
    # Fallback: chat completion without web search tool
    completion = await async_client.chat.completions.create(
        model=model_name,
        messages=_flatten_messages(input_prompt),
    )
    return _CompatResponse(completion)


def modify_prompts_for_provenance_decorator(
    additional_system_instruction="""
---

**Understand Input Structure of the citable document text:**

Each input will be a legal document where:

- The first part is the **statement**: This is the main argument or claim being made in the brief. It will be a single sentence or a short paragraph.
- The second part is the **biomarker**: This is a complete, unique identifier for the immediately preceding statement. The required format is:  
  `(biomarker: ||<label>|| <letter>-<complete unique identifier>)`  
  - `<label>` must appear **exactly** as it is in the input (e.g., the document title or case name, with no substitutions or abbreviations).

**Example:**

**❌ Do NOT do this:**  
`This is the statement text (<label>: biomarker: <human readable bluebook citation>).`

**✅ Instead, do this:**  
`This is the statement text. (biomarker: ||<label>|| <letter>-<complete unique identifier>)`
`This is the next statement text. (biomarker: ||<label>|| <letter>-<complete unique identifier>)`
...and so on.

---

**HARD RULES FOR BIOMARKER HANDLING** (DO NOT BREAK):

1. **Exact Reproduction**:  
   Always use the **biomarker label and unique identifier** exactly as present in the input.  
   - Do not alter, abbreviate, combine, or fabricate labels or identifiers in any way.

2. **Format Consistency and Purity**:  
   The biomarker must match the pattern:  
   `(biomarker: ||<label>|| <letter>-<complete unique identifier>)`
   - **Absolutely nothing else** may appear inside or before the biomarker span; do not add any words or text inside or adjacent to the biomarker parentheses (e.g., never "(see above, biomarker: ...)" or "(as previously described; see biomarker: ...)"). The biomarker citation must **stand alone** in its parentheses, with no additional text contained in or directly adjacent to it.
   - Never introduce, omit, or modify any part of this format.
   - Never use angle brackets `<` or `>` in the actual output.

3. **Content Restriction**:  
   Only cite biomarkers connected to substantive statements (complete sentences or paragraphs).
   - **Never cite**: headers, section numbers, titles, footers, case names, footnotes, or any kind of non-statement text.
   - If citing a short sentence is necessary, include the biomarker for the next statement as well.

4. **Strict Non-Fabrication**:  
   Never fabricate, guess, or complete a biomarker.  
   - If required information is missing, **do not attempt to fill it in**.

5. **Citation Validity**:
   - If citing multiple biomarkers, separate them with a semicolon and a space, like this:
     `(biomarker: ||<label>|| <letter>-<complete unique identifier>); (biomarker: ||<label>|| <letter>-<complete unique identifier>)`
   - Every biomarker citation must be attached only to the corresponding source statement, and must not be moved between unrelated statements.

6. **Placement Flexibility**:  
   - Biomarker citations may appear at any logical point in your output statement, not just at the end—ensure they fit naturally and clearly reference the supporting statement. The sentence's punctuation should come before the biomarker, not after it.

---

**Failure to precisely follow these instructions will result in output being rejected as unusable.** 
- Any deviation, fabrication, or reformatting will be treated as an error.


---

**Stability Techniques You Must Follow:**

- Always cross-check biomarker labels and identifiers for **exact string match** to input.
- Reject or flag any output if the biomarker is missing, incomplete, or altered in any way.
- Refuse any output if the input format (statement + newline + valid biomarker) is not strictly followed.
- Ignore and do not process inputs with invalid or ambiguous labels or identifiers.
- If the content is too vague to warrant a citation, provide a general statement and give **no citation**.

---

**Example Input:**  
```
<Example statement text>
(biomarker: ||<label>|| <letter>-<complete unique identifier>)
<Next statement text>
(biomarker: ||<label>|| <letter>-<complete unique identifier>)
```

**Example Output:**  
```
Based on the finding in (biomarker: ||<label>|| <letter>-<complete unique identifier>), the court determined precedent was not applicable.
```
or 
``` 
The (biomarker: ||<label>|| <letter>-<complete unique identifier>) supports the conclusion that the defendant’s interpretation was invalid.
```
or 
``` 
The court found that the defendant’s reliance on precedent was misplaced. (biomarker: ||<label>|| <letter>-<complete unique identifier>) The statute backs this up. (biomarker: ||<label>|| <letter>-<complete unique identifier>)
```

---

**REMEMBER:**  
- **Do not invent** or "complete" any part of a biomarker.
- **Never** add any words inside or directly before biomarker citation parentheses.
- **Always** use biomarker data exactly as in supplied input.
- **Never** cite to anything but substantive statements.

---

**These rules are absolute. No exceptions.**  
""",
    additional_note="""
- Never respond in a bulleted format
- Always use the exact label and unique identifier from the input for each citation, in this precise format: (biomarker: ||<label>|| <letter>-<complete unique identifier>)
- The label for any cited biomarker MUST be an exact string match to its appearance in the input. Never substitute, abbreviate, combine, or alter labels or identifiers in any way.
- Biomarker citations may appear at any logical place within a drafted sentence. Place the citation where it most directly supports the statement or reasoning.
- The chosen biomarker must reference the legal statement from the input document that directly supports the sentence you are writing.
- Only cite biomarkers assigned to substantive statements (e.g., paragraphs or long sentences). Do not cite to biomarkers for titles, headers, case names, numbers, footers, or any non-statement text. If citing a short sentence's biomarker, also cite the biomarker for the next relevant substantive statement.
- When using more than one biomarker, separate each citation with a semicolon and a space: (biomarker: ||<label>|| <letter>-<complete unique identifier>); (biomarker: ||<label>|| <letter>-<complete unique identifier>)
- Never fabricate, modify, or truncate a biomarker, and never invent missing parts. Use only the full, exact identifiers and labels as provided in the input.
- Do not use any of the following incorrect formats:
    - Biomarkers missing required letters or numbers.
    - Biomarkers with extra or altered characters.
    - Label-identifier pairs not present in the input.
    - Biomarkers for section headers, page numbers, title lines, footnotes, document metadata, or any non-statement content.
    - **Never add any commentary, explanation, or transitional phrase inside the biomarker citation’s parentheses.**
    - **Never use a partial, broken, empty, or incomplete biomarker span. For string cites, every biomarker must be complete, separated only by semicolon and space as shown above.**
- The characters `<` and `>` must never appear in your output under any circumstances.
- Review each drafted sentence to ensure every included biomarker is contextually relevant, accurately formatted, and strictly tied to the supporting input statement.
- If there is insufficient information for a citation or if no valid biomarker is available, leave the sentence uncited rather than using an incorrect or fabricated reference.
- Adherence to these citation and formatting rules is mandatory. Any deviation may invalidate the output.
- Each statement is always immediately followed by its respective biomarker in parentheses. The biomarker belongs only to the statement that immediately precedes it. Under no circumstances does a biomarker refer to or follow a different statement. No statement is ever preceded by its biomarker.
""",
    additional_user_prompt="""
Remember:

NEVER fabricate, truncate, or alter a biomarker.
NEVER add any explanatory text, commentary, or words inside the biomarker citation parentheses (i.e., do not use phrases such as "see", "as above", or "see biomarker:" or similar constructions).
Use only the exact identifiers and labels supplied in the input.

Citation Rules (apply to every sentence where citation is possible):

Always cite using the exact format: 'Example statement. (biomarker: ||<label>|| <letter>-<complete unique identifier>)'
When using multiple biomarkers in a sentence (string cite), separate citations with a semicolon and a space: 'Example statement. (biomarker: ||<label>|| <letter>-<complete unique identifier>); (biomarker: ||<label>|| <letter>-<complete unique identifier>)'
Never use made-up or "fixed" biomarkers for missing, incomplete, or partially matching citations—omit such citations entirely.
Never allow any broken, unclosed, empty, or partial biomarker spans; citations must be complete and match the prescribed format.
Never include incorrectly formatted or incomplete string cites—each biomarker in a string cite must be full and perfectly formatted, or none should be included.
Failure to adhere to ANY of these rules will result in the output being rejected as unusable.
""",
):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            input_messages = kwargs.get("input_prompt", None)
            # Defensive check: if 'input' is not in kwargs, try to find in args by signature guessing (optional)
            # For this example, we require 'input' as kwarg to modify
            if input_messages and isinstance(input_messages, list):
                # Modify system message
                for msg in input_messages:
                    if msg.get("role") == "system":
                        content_list = msg.get("content", [])
                        if content_list and isinstance(content_list, list):
                            # Find the first dict with type 'input_text'
                            for c in content_list:
                                # Guard against future changes by accepting both variants
                                if (
                                    c.get("type") in {"input_text", "text"}
                                    and "text" in c
                                ):
                                    text = c["text"]

                                    # Prepend additional system instruction if given and not already present
                                    if (
                                        additional_system_instruction
                                        and additional_system_instruction.strip()
                                    ):
                                        # Add a separating newline for clarity if needed
                                        separator = (
                                            "\n"
                                            if not additional_system_instruction.endswith(
                                                "\n"
                                            )
                                            else ""
                                        )
                                        c["text"] = (
                                            additional_system_instruction
                                            + separator
                                            + text
                                        )

                                    # Search for 'Notes:\n' or 'notes:\n' to insert additional note
                                    # Regexp to find Notes: or notes: followed by \n (case insensitive)
                                    pattern = re.compile(r"(Notes:)", re.IGNORECASE)
                                    match = pattern.search(c["text"])
                                    if match:
                                        # Insert additional note after Notes:\n line
                                        insert_pos = match.end()
                                        # Check if note already exists to avoid duplication
                                        if additional_note not in c["text"]:
                                            c["text"] = (
                                                c["text"][:insert_pos]
                                                + additional_note
                                                + "\n"
                                                + c["text"][insert_pos:]
                                            )
                                    else:
                                        # Append note at end if none found (and not duplicating)
                                        if (
                                            additional_note
                                            and additional_note.strip()
                                            and additional_note not in c["text"]
                                        ):
                                            # Add with preceding newline for spacing if needed
                                            if not c["text"].endswith("\n"):
                                                c["text"] += "\n"
                                            c["text"] += additional_note + "\n"
                                    break
                        break  # Assume only one system message to modify

                # Modify last user message
                # Find last user entry in the list
                last_user_msg = None
                for i in range(len(input_messages) - 1, -1, -1):
                    if input_messages[i].get("role") == "user":
                        last_user_msg = input_messages[i]
                        break
                if last_user_msg:
                    content_list = last_user_msg.get("content", [])
                    if content_list and isinstance(content_list, list):
                        for c in reversed(content_list):
                            if c.get("type") in {"input_text", "text"} and "text" in c:
                                # Append additional user prompt if given
                                if (
                                    additional_user_prompt
                                    and additional_user_prompt.strip()
                                ):
                                    # add newline if needed
                                    if not c["text"].endswith(
                                        "\n"
                                    ) and not additional_user_prompt.startswith("\n"):
                                        c["text"] += "\n"
                                    c["text"] += additional_user_prompt
                                break

            return await func(*args, **kwargs)

        return wrapper

    return decorator


@modify_prompts_for_provenance_decorator()
async def ask_gpt_chat_completion_with_biomarkers(*, input_prompt: list[dict], model: str, **kwargs):
    return await async_client.chat.completions.create(
        model=model,
        messages=input_prompt,
        **kwargs,
    )


async def ask_gpt_chat_completion_no_biomarkers(*, input_prompt: list[dict], model: str, **kwargs):
    return await async_client.chat.completions.create(
        model=model,
        messages=input_prompt,
        **kwargs,
    )


@modify_prompts_for_provenance_decorator()
async def ask_gpt_file_search_with_citation_modifier(input_prompt, model_name="gpt-4.1", vs_id=None):
    response = await async_client.chat.completions.create(
        model=model_name,
        messages=input_prompt,
        temperature=1,
        max_tokens=16000,
        top_p=1,
        tools=[{"type": "file_search", "file_ids": [vs_id]}] if vs_id else [],
    )
    return response if response else "No response generated."


async def ask_gpt_no_citation_modifier(input_prompt, model_name="gpt-4.1", vs_id=None):
    response = await async_client.chat.completions.create(
        model=model_name,
        messages=input_prompt,
        temperature=1,
        max_tokens=16000,
        top_p=1,
        tools=[{"type": "file_search", "file_ids": [vs_id]}] if vs_id else [],
    )
    return response if response else "No response generated."


async def ask_gpt_file_search(input_prompt, model_name="gpt-4.1", vs_id=None, reasoning=None):
    if _has_responses_api():
        response = await async_client.responses.create(
            model=model_name,
            input=input_prompt,
            temperature=1,
            max_output_tokens=16000,
            top_p=1,
            tools=[{"type": "file_search", "vector_store_ids": [vs_id]}] if vs_id else [],
            reasoning={"effort": reasoning, "summary": "auto"} if reasoning else {},
            store=True,
        )
        return response if response else "No response generated."
    completion = await async_client.chat.completions.create(
        model=model_name,
        messages=_flatten_messages(input_prompt),
        temperature=1,
    )
    return _CompatResponse(completion)


@modify_prompts_for_provenance_decorator()
async def ask_gpt_content_prediction(input_prompt, model_name="gpt-4.1", prediction=""):
    completion = await async_client.chat.completions.create(
        model=model_name,
        messages=input_prompt,
        prediction={"type": "content", "content": prediction},
        temperature=0.26,
        max_tokens=32768,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0,
    )
    return completion if completion else "No response generated."


# ---------------------------------------------------------------------------
# Streaming driver (sync) — used by the chat UI scaffold
# ---------------------------------------------------------------------------


def stream_gpt_web_responses(
    *,
    input_prompt: list[dict],
    model_name: str = "gpt-5.1",
    effort: str = "low",
    verbosity: str = "medium",
    on_delta: Optional[Callable[[str], None]] = None,
    on_reasoning_delta: Optional[Callable[[str, str], None]] = None,
    on_tool_event: Optional[Callable[[str, dict], None]] = None,
    event_recorder: Optional[Callable[[dict], None]] = None,
    enable_web_search: bool = True,
    max_tool_calls: int = 3,
) -> str:
    """Stream using Chat Completions by default for broad model compatibility.

    Set env WILLIT_STREAM_MODE=responses to use the Responses API streaming;
    otherwise use chat.completions streaming (which avoids unsupported params and
    works with most models).
    """
    default_mode = "responses" if _has_responses_api() else "chat"
    mode = (os.getenv("WILLIT_STREAM_MODE") or default_mode).lower()
    messages = _flatten_messages(input_prompt)

    if mode == "responses" and _has_responses_api():
        final_response_text = ""
        allow_reasoning = os.getenv("WILLIT_STREAM_REASONING", "true").lower() == "true"
        effort_value = (effort or "").strip().lower()
        enable_reasoning = allow_reasoning and effort_value not in ("", "none")
        stream_kwargs: dict[str, Any] = {}
        if enable_reasoning:
            stream_kwargs["reasoning"] = {"effort": effort_value or "medium", "summary": "auto"}
            stream_kwargs["include"] = ["reasoning.encrypted_content"]
            stream_kwargs["text"] = {"verbosity": verbosity}
        else:
            stream_kwargs["text"] = {"verbosity": verbosity}
        if event_recorder:
            event_recorder({"phase": "responses_stream_start", "mode": mode, "model": model_name})
        tool_payload: list[dict] = []
        if enable_web_search:
            tool_payload.append(
                {
                    "type": "web_search_preview",
                    "user_location": {"type": "approximate"},
                    "search_context_size": "medium",
                }
            )
        tool_payload.append(
            {
                "type": "function",
                "name": "drafter",
                "description": "update the draft using this tool, it Renders or update the running will draft using markdown.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "section": {"type": "string", "description": "Draft section key, e.g., 'intro', 'executors'"},
                        "title": {"type": "string", "description": "Section title to show in the draft widget"},
                        "markdown": {"type": "string", "description": "Markdown content to render"},
                    },
                    "required": ["markdown"],
                },
            }
        )
        max_tool_calls_param = max_tool_calls if enable_web_search else 1
        with sync_client.responses.stream(
            model=model_name,
            input=input_prompt,
            tools=tool_payload or None,
            max_tool_calls=max_tool_calls_param,
            **stream_kwargs,
        ) as stream:
            for event in stream:
                etype = getattr(event, "type", "")
                if event_recorder:
                    payload = {"event_type": etype}
                    for attr in ("server_label", "tool", "tool_name", "name", "status"):
                        val = getattr(event, attr, None)
                        if isinstance(val, str):
                            payload.setdefault("details", {})[attr] = val
                    event_recorder(payload)
                if etype == "response.output_text.delta":
                    if on_delta:
                        on_delta(getattr(event, "delta", ""))
                elif etype in (
                    "response.reasoning_text.delta",
                    "response.reasoning_summary_text.delta",
                ):
                    delta = getattr(event, "delta", "")
                    if not delta:
                        continue
                    variant = (
                        "summary" if etype == "response.reasoning_summary_text.delta" else "reasoning"
                    )
                    if on_reasoning_delta:
                        on_reasoning_delta(delta, variant)
                elif on_tool_event and (
                    ".tool" in etype
                    or ".search" in etype
                    or etype.startswith("response.mcp_")
                    or "function_call" in etype
                ):
                    payload: dict[str, Any] = {}
                    details: dict[str, str] = {}
                    for attr in ("server_label", "tool", "tool_name", "name", "status"):
                        val = getattr(event, attr, None)
                        if isinstance(val, str):
                            details[attr] = val
                    arg_text = getattr(event, "arguments", None)
                    delta_text = getattr(event, "delta", None)
                    if isinstance(arg_text, str):
                        details["arguments"] = arg_text
                    elif isinstance(delta_text, str):
                        details["arguments"] = delta_text
                    payload["details"] = details
                    on_tool_event(etype, payload)
            response = stream.get_final_response()
            final_response_text = response.output_text
            if event_recorder:
                event_recorder({"phase": "responses_stream_end", "mode": mode})
        return final_response_text

    # Chat Completions streaming
    def _lcp_len(a: str, b: str) -> int:
        """Longest common prefix length for two strings."""
        n = min(len(a), len(b))
        i = 0
        while i < n and a[i] == b[i]:
            i += 1
        return i

    def _overlap_suffix_prefix(a: str, b: str, max_check: int = 200) -> int:
        """Return k where a.endswith(b[:k]) and k is maximal (<= max_check).

        Helps avoid duplicating when a delta piece repeats the tail of emitted.
        """
        max_k = min(len(b), max_check, len(a))
        for k in range(max_k, 0, -1):
            if a.endswith(b[:k]):
                return k
        return 0

    emitted = ""
    # Use the most compatible signature – some models reject sampling/penalty params.
    if event_recorder:
        event_recorder({"phase": "chat_stream_start", "model": model_name})
    stream = sync_client.chat.completions.create(
        model=model_name,
        messages=messages,
        stream=True,
    )
    for chunk in stream:
        piece = ""
        # Preferred: incremental delta
        try:
            piece = chunk.choices[0].delta.content or ""
        except Exception:
            piece = ""

        if piece:
            # Append only the non-overlapping suffix to avoid repeats
            k = _overlap_suffix_prefix(emitted, piece)
            new_piece = piece[k:]
            if new_piece:
                emitted += new_piece
                if on_delta:
                    on_delta(new_piece)
            continue

        # Fallback: some clients send cumulative message content per chunk
        try:
            cumulative = chunk.choices[0].message.content or ""
        except Exception:
            cumulative = ""
        if cumulative:
            # Compute only the newly added suffix using LCP to avoid duplication
            lcp = _lcp_len(emitted, cumulative)
            new_part = cumulative[lcp:]
            emitted = cumulative
            if on_delta and new_part:
                on_delta(new_part)
        if event_recorder:
            event_recorder({"event_type": "chat_chunk", "has_piece": bool(piece), "has_cumulative": bool(cumulative)})

    if event_recorder:
        event_recorder({"phase": "chat_stream_end"})
    return emitted
