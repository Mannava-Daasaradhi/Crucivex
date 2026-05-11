import base64
import hashlib
import logging
import sys
from pathlib import Path

import fitz
import pdfplumber
import pytesseract
import requests
from PIL import Image

# ── Tunable thresholds ─────────────────────────────────────────────────────────
PDFPLUMBER_MIN_CHARS = 50       # tier 1 gate: below this → render + OCR
TESSERACT_MIN_CONF   = 60.0     # tier 2 gate: below this → vision model
RENDER_SCALE         = 2        # PyMuPDF render resolution multiplier
OLLAMA_MODEL         = "moondream"
OLLAMA_URL           = "http://localhost:11434/api/generate"
OLLAMA_TIMEOUT       = 60       # seconds before Ollama call is abandoned

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)


# ── Rendering ──────────────────────────────────────────────────────────────────

def render_page_image(fitz_doc: fitz.Document, page_num: int, out_dir: Path) -> Path:
    """Render one page from an already-open fitz.Document. No repeated open/close."""
    page     = fitz_doc[page_num]
    pix      = page.get_pixmap(matrix=fitz.Matrix(RENDER_SCALE, RENDER_SCALE))
    img_path = out_dir / f"page_{page_num + 1}.png"
    pix.save(str(img_path))
    return img_path


# ── Tier extractors ────────────────────────────────────────────────────────────

def extract_text_with_tesseract(img_path: Path) -> tuple[str, float]:
    data = pytesseract.image_to_data(
        Image.open(img_path), output_type=pytesseract.Output.DICT
    )
    # FIX: use the same threshold (> 0) for both the mean and the word filter
    confidences = [int(c) for c in data["conf"] if c != "-1" and int(c) > 0]
    text = " ".join(
        w for w, c in zip(data["text"], data["conf"])
        if c != "-1" and int(c) > 0 and w.strip()
    )
    mean_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return text, mean_conf


def extract_text_with_vision(img_path: Path) -> str:
    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model":  OLLAMA_MODEL,
                "prompt": (
                    "Extract all text from this image exactly as written. "
                    "Return only the text. No commentary. No formatting."
                ),
                "images": [img_b64],
                "stream": False,
            },
            timeout=OLLAMA_TIMEOUT,
        )
        response.raise_for_status()
        return response.json().get("response", "")
    except requests.RequestException as e:
        log.error(f"Ollama request failed: {e}")
        return ""


# ── Deduplication ──────────────────────────────────────────────────────────────

def deduplicate(text: str) -> str:
    seen, result = set(), []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        h = hashlib.md5(block.encode()).hexdigest()
        if h not in seen:
            seen.add(h)
            result.append(block)
    return "\n\n".join(result)


# ── Page extraction ────────────────────────────────────────────────────────────

def extract_page(
    plumber_pdf: pdfplumber.PDF,
    fitz_doc: fitz.Document,
    page_num: int,
    data_dir: Path,
) -> dict:
    """
    Extract and deduplicate text from one page using the tiered pipeline.
    Receives already-open PDF handles — no repeated open/close per page.

    Returns:
        {
            "page":       int,          -- 1-indexed
            "text":       str,          -- clean deduplicated text
            "tier":       int,          -- 1 | 2 | 3
            "confidence": float | None, -- tesseract mean conf (tiers 2+), else None
            "error":      str | None    -- set only on failure
        }
    """
    # Tier 1: pdfplumber (zero rendering cost)
    raw = plumber_pdf.pages[page_num].extract_text() or ""

    if len(raw.strip()) > PDFPLUMBER_MIN_CHARS:
        log.info(f"  page {page_num + 1}: tier 1 (pdfplumber)")
        return {"page": page_num + 1, "text": deduplicate(raw), "tier": 1, "confidence": None, "error": None}

    # Tier 2+: need a rendered image
    img_path = render_page_image(fitz_doc, page_num, data_dir)
    try:
        text, conf = extract_text_with_tesseract(img_path)
        log.info(f"  page {page_num + 1}: tier 2 (tesseract) conf={conf:.1f}")

        if conf >= TESSERACT_MIN_CONF:
            return {"page": page_num + 1, "text": deduplicate(text), "tier": 2, "confidence": round(conf, 1), "error": None}

        # Tier 3: vision model
        log.info(f"  page {page_num + 1}: tier 3 (moondream) — tesseract conf too low ({conf:.1f})")
        text = extract_text_with_vision(img_path)
        return {"page": page_num + 1, "text": deduplicate(text), "tier": 3, "confidence": round(conf, 1), "error": None}

    finally:
        # Always clean up the temp image — do not accumulate PNGs
        try:
            img_path.unlink()
        except OSError:
            pass


# ── Document extraction ────────────────────────────────────────────────────────

def extract_text(pdf_path: str, verbose: bool = False) -> list[dict]:
    """
    Extract text from every page of a PDF.

    Args:
        pdf_path: Path to the PDF file.
        verbose:  If True, print each page's extracted text to stdout.

    Returns a list of page result dicts (see extract_page).
    Pages that fail are included with text="" and error set — pipeline never stops on one bad page.
    """
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    results = []

    # Open both handles once — reused across all pages, never reopened per page
    with pdfplumber.open(pdf_path) as plumber_pdf:
        num_pages = len(plumber_pdf.pages)
        fitz_doc  = fitz.open(pdf_path)
        try:
            for i in range(num_pages):
                log.info(f"\n--- Page {i + 1} / {num_pages} ---")
                try:
                    result = extract_page(plumber_pdf, fitz_doc, i, data_dir)
                except Exception as e:
                    log.error(f"  page {i + 1}: extraction failed — {e}")
                    result = {"page": i + 1, "text": "", "tier": None, "confidence": None, "error": str(e)}
                results.append(result)
                if verbose:
                    print(result["text"])
        finally:
            fitz_doc.close()

    return results


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_text.py <pdf_path> [--verbose]")
        sys.exit(1)
    verbose = "--verbose" in sys.argv
    extract_text(sys.argv[1], verbose=verbose)