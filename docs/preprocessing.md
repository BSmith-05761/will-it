# Preprocessing Pipeline (Nimble)

Goal: Convert raw uploads into LLM‑optimized, biomarked plain text blocks. Prefer DOCX and TXT; accept PDFs; fallback to page snapshots + multimodal when text extraction is poor.

## Inputs
- One or more uploaded files with `{ filename, bytes, doc_type?, display_name? }`.
- Supported types (preference order): `txt`, `docx`, `pdf`, images (`png`, `jpg`, `jpeg`, `tiff`).

## Steps
- Detect type from extension (nimble). Optionally refine via magic later.
- Extract text:
  - TXT: decode as UTF‑8 with `errors="replace"`.
  - DOCX: read paragraphs via `python-docx`.
  - PDF: try text via `pypdf` or `pdfminer.six`.
  - Images/PDF pages (OCR): `pytesseract` + `PIL` (and `pdf2image` for PDF rasterization).
- Quality check (heuristics):
  - Empty or near‑empty text.
  - High garble ratio: low alnum share, lots of ligatures/diacritics, illegible character patterns.
  - If poor text from PDF: rasterize → OCR; recompute quality.
  - If still poor: mark `mode: snapshots` and include page images for multimodal.
- Biomarkers:
  - Split text on `\n\n` boundaries.
  - For each segment, append a trailing biomarker `mrkr||<document_name>||d-<hex>` where `<hex>` is a stable short hash of the segment.
  - Join segments with `\n\n` preserved.
- Wrap each document:
  - `Start of document, <Document name/title/type>\n\n<biomarked text>\n\nEnd of document`
- Aggregate all wrapped docs into one plain text payload.

## Outputs
- `text` (string): concatenated wrapped, biomarked documents.
- `documents` (list): per‑doc info `{ name, type, biomarker_count, quality: { score, reason, method }, mode: "text|ocr|snapshots", pages?, ocr_attempted }`.
- When `mode: snapshots`, include `snapshots[]` (image bytes or opaque references) for multimodal prompts.

## Biomarker Format
- Exact token: `mrkr||<document_name>||d-<hex>`
- `mrkr` literal must always exist.
- `<document_name>`: stable display name; avoid punctuation if possible.
- `<hex>`: lowercase hex (e.g., first 10 of SHA1 of `document_name + "::" + segment`).
- Biomarker placement: appended at the end of every `\n\n`-segmented chunk.

## Dependencies (optional, pluggable)
- `python-docx` for DOCX, `pypdf` or `pdfminer.six` for PDFs.
- `Pillow` + `pytesseract` (and Tesseract installed) for OCR.
- `pdf2image` (plus `poppler`) to rasterize PDFs to images.

## Failure Modes
- Missing optional libs: degrade gracefully; flag `mode: snapshots` when text is unusable.
- Very large files: truncate or page‑limit OCR with clear note in `quality.reason`.

Use `backend/willit/preprocessing.py` for the reference implementation; keep it nimble and dependency‑optional.

