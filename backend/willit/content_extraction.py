import re

_ANCHOR_PATTERN = re.compile(r"<a\b[^>]*>.*?</a>", flags=re.IGNORECASE | re.DOTALL)
_SPAN_OPEN_VALIDATION_PATTERN = re.compile(
    r'<span\s+[^>]*data-validation-result-ids="[^"]*"[^>]*>', flags=re.IGNORECASE
)
_SPAN_CLOSE_PATTERN = re.compile(r"</span>", flags=re.IGNORECASE)
_GENERIC_TAG_PATTERN = re.compile(r"<[^>]+>")


def clean_html(text: str) -> str:
    """Remove anchors and validation spans; strip other tags; normalize whitespace.

    Mirrors learned-hand analyze fallback with regex only (no BeautifulSoup required).
    """
    if not isinstance(text, str):
        return text
    cleaned = _ANCHOR_PATTERN.sub("", text)
    cleaned = _SPAN_OPEN_VALIDATION_PATTERN.sub("", cleaned)
    cleaned = _SPAN_CLOSE_PATTERN.sub("", cleaned)
    cleaned = _GENERIC_TAG_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def extract_content(data) -> str:
    """Traverse nested JSON-like structures and join any 'content' fields.

    - Looks for dicts and lists recursively.
    - When 'content' is a string, cleans HTML and collects it.
    - When 'children' is a list, descends.
    - Returns a single string joined by newlines.
    """
    out: list[str] = []

    def _walk(obj):
        if obj is None:
            return
        if isinstance(obj, list):
            for item in obj:
                _walk(item)
            return
        if not isinstance(obj, dict):
            return
        for k, v in obj.items():
            if k == "content":
                if isinstance(v, str):
                    out.append(clean_html(v))
                elif isinstance(v, dict) and "content" in v:
                    val = v.get("content")
                    out.append(clean_html(val if isinstance(val, str) else str(val)))
            elif k == "children" and isinstance(v, list):
                for child in v:
                    _walk(child)
            else:
                _walk(v)

    _walk(data)
    return "\n".join(out).strip()

