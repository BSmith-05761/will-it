"""Preprocessing pipeline: raw files -> LLM-optimized biomarked text.

Design goals
- Prefer DOCX/TXT over PDF for text extraction.
- Accept PDFs; if text quality is poor, OCR or fall back to snapshots for multimodal.
- Split text on double newlines and append biomarkers of the form:
  【mrkr||<document_name>||d-<hex>】
- Wrap each document with:
  Start of document, <Document name/title/type>

  <biomarked text>

  End of document

This module is nimble: optional dependencies; degrade gracefully when missing.
"""

from __future__ import annotations

import hashlib
import io
import re
from typing import Any, Dict, List, Optional, Tuple
import base64


def _guess_ext(filename: str) -> str:
    return (filename.rsplit(".", 1)[-1] or "").lower() if "." in filename else ""


def _decode_txt(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")


def _docx_to_text(data: bytes) -> str:
    try:
        from docx import Document  # type: ignore

        doc = Document(io.BytesIO(data))
        paras = [p.text for p in doc.paragraphs]
        return "\n".join(paras)
    except Exception:
        return ""


def _pdf_to_text(data: bytes) -> Tuple[str, int]:
    """Try to extract text from PDF. Return (text, page_count)."""
    # Attempt pypdf first (fast for simple docs)
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:
                pages.append("")
        return "\n\n".join(pages), len(reader.pages)
    except Exception:
        pass
    # Fallback: pdfminer.six
    try:
        from pdfminer.high_level import extract_text  # type: ignore

        text = extract_text(io.BytesIO(data))
        # pdfminer doesn't give page count easily here; leave unknown (-1)
        return text or "", -1
    except Exception:
        return "", -1


def _pdf_to_images(data: bytes) -> List["Image.Image"]:
    images: List["Image.Image"] = []
    try:
        from pdf2image import convert_from_bytes  # type: ignore

        images = convert_from_bytes(data)
    except Exception:
        images = []
    return images


def _image_bytes_to_text(img_bytes: bytes) -> str:
    try:
        from PIL import Image  # type: ignore
        import pytesseract  # type: ignore

        with Image.open(io.BytesIO(img_bytes)) as im:
            return pytesseract.image_to_string(im) or ""
    except Exception:
        return ""


def _images_to_ocr_text(images: List["Image.Image"]) -> str:
    try:
        import pytesseract  # type: ignore

        texts = []
        for im in images:
            try:
                texts.append(pytesseract.image_to_string(im) or "")
            except Exception:
                texts.append("")
        return "\n\n".join(texts)
    except Exception:
        return ""


def _quality_score(text: str, page_count: int | None = None) -> Tuple[float, str]:
    """Heuristic quality scoring: higher is better.

    Factors:
    - length
    - alnum ratio vs. strange chars
    - newlines/spacing balance
    Also uses page_count to detect near-empty PDFs.
    """
    t = text or ""
    L = len(t)
    if L == 0:
        return 0.0, "empty"
    alnum = sum(ch.isalnum() for ch in t)
    alnum_ratio = alnum / max(1, L)
    newlines = t.count("\n")
    # crude: penalize very low alnum ratio
    score = 0.4 * min(1.0, L / 2000.0) + 0.5 * alnum_ratio + 0.1 * (1.0 - min(1.0, newlines / max(1, L)))
    reason = f"len={L}, alnum_ratio={alnum_ratio:.2f}, newlines={newlines}"
    if page_count and page_count > 0 and L / page_count < 100:  # near-empty per page
        score *= 0.5
        reason += f", penalized:low_chars_per_page({L/page_count:.1f})"
    return max(0.0, min(score, 1.0)), reason


def _make_biomarker(document_name: str, segment: str) -> str:
    # stable short hash of name + segment
    digest = hashlib.sha1((document_name + "::" + segment).encode("utf-8", "ignore")).hexdigest()[:10]
    return f"【mrkr||{document_name}||d-{digest}】"


def _biomark_text(text: str, document_name: str) -> Tuple[str, int]:
    """Split on double newlines, append biomarker to each segment, and rejoin."""
    # Normalize CRLF
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    segments = re.split(r"\n{2,}", normalized)
    marked_segments: List[str] = []
    for seg in segments:
        seg_clean = seg.strip("\n")
        if not seg_clean:
            continue
        marker = _make_biomarker(document_name, seg_clean)
        # Append marker at end of the segment
        if seg_clean.endswith("\n"):
            marked = f"{seg_clean}{marker}"
        else:
            marked = f"{seg_clean} {marker}"
        marked_segments.append(marked)
    return "\n\n".join(marked_segments), len(marked_segments)


def _wrap_document_block(name: str, doc_type: str, biomarked_text: str) -> str:
    header = f"Start of document, {name} | {doc_type}"
    footer = "End of document"
    return f"{header}\n\n{biomarked_text}\n\n{footer}"


IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}


def _image_to_png_base64(data: bytes) -> Tuple[str, str]:
    """Convert arbitrary image bytes to PNG base64 for consistent previews."""
    try:
        from PIL import Image  # type: ignore

        with Image.open(io.BytesIO(data)) as im:
            converted = im.convert("RGBA") if im.mode in ("RGBA", "LA") else im.convert("RGB")
            buffer = io.BytesIO()
            converted.save(buffer, format="PNG")
            encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
            return encoded, "image/png"
    except Exception:
        return base64.b64encode(data).decode("ascii"), "image/png"


def preprocess_document(*, filename: str, blob: bytes, doc_type: str | None = None, display_name: str | None = None) -> Dict[str, Any]:
    """Preprocess a single document to biomarked text.

    Returns a dict with:
      - name, type, text_block (wrapped biomarked text), biomarker_count
      - quality {score, reason, method}
      - mode: "text" | "ocr" | "snapshots"
      - snapshots: optional list of image objects or bytes (impl-dependent)
    """
    ext = _guess_ext(filename)
    name = display_name or filename
    typ = doc_type or ext or "unknown"

    text = ""
    method = ""
    page_count: Optional[int] = None
    snapshots: List[Any] | None = None
    image_base64: Optional[str] = None
    image_mime: Optional[str] = None

    if ext in ("txt",):
        text = _decode_txt(blob)
        method = "txt"
    elif ext in ("docx",):
        text = _docx_to_text(blob)
        method = "docx"
    elif ext in ("pdf",):
        text, pc = _pdf_to_text(blob)
        page_count = pc if pc and pc > 0 else None
        method = "pdf_text"
        # Prefer OCR if text quality is bad
        score, _ = _quality_score(text, page_count)
        if score < 0.45:  # threshold tuned for nimble default
            images = _pdf_to_images(blob)
            if images:
                ocr_text = _images_to_ocr_text(images)
                ocr_score, _ = _quality_score(ocr_text, len(images))
                if ocr_score > score:
                    text = ocr_text
                    method = "pdf_ocr"
                else:
                    # keep worse text but signal snapshots for multimodal
                    snapshots = images
                    method = "pdf_snapshots"
            else:
                method = "pdf_text_poor"
    elif ext in IMAGE_EXTENSIONS:
        text = _image_bytes_to_text(blob)
        method = "image_ocr"
        page_count = 1
        image_base64, image_mime = _image_to_png_base64(blob)
    else:
        # Unknown type: try UTF-8 decode
        text = _decode_txt(blob)
        method = "unknown_utf8"

    score, reason = _quality_score(text, page_count)

    mode = "text"
    if method in ("pdf_ocr", "image_ocr"):
        mode = "ocr"
    if method in ("pdf_snapshots",) and snapshots:
        mode = "snapshots"

    # If still very poor, and we have PDF pages, enforce snapshots mode
    if score < 0.3 and ext == "pdf" and snapshots is None:
        imgs = _pdf_to_images(blob)
        if imgs:
            snapshots = imgs
            mode = "snapshots"
            reason += ", forced_snapshots_for_multimodal"

    biomarked_text, count = _biomark_text(text or "", name)
    block = _wrap_document_block(name, typ, biomarked_text)

    return {
        "name": name,
        "type": typ,
        "text_block": block,
        "biomarker_count": count,
        "quality": {"score": score, "reason": reason, "method": method},
        "mode": mode,
        "snapshots": snapshots,
        "page_count": page_count,
        "ocr_attempted": method in ("pdf_ocr", "image_ocr"),
        "image_base64": image_base64,
        "mime_type": image_mime,
    }


def preprocess_documents(documents: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Preprocess a batch of documents.

    documents: list of dicts with keys:
      - filename (str)
      - blob (bytes)
      - doc_type (optional str)
      - display_name (optional str)

    Returns dict with keys:
      - text (concatenated wrapped biomarked text)
      - documents (list of per-doc results)
    """
    results = []
    blocks = []
    for d in documents:
        res = preprocess_document(
            filename=d.get("filename", "unknown"),
            blob=d.get("blob", b""),
            doc_type=d.get("doc_type"),
            display_name=d.get("display_name"),
        )
        results.append(res)
        blocks.append(res.get("text_block", ""))
    return {"text": "\n\n".join(b for b in blocks if b), "documents": results}
