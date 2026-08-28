"""
End to end: PDF in, renderable world out.

    python -m core.pipeline data/manual.pdf --title "Honda GX160 - short block"

Runs the tiered text extraction, decodes an Assembly, puts it through the
falsification checks, renders images only for the pages something actually
cites, and writes everything the viewer needs into web/.

The checks run before anything is written. A world that fails a fatal property
is still written out -- we want to be able to look at it -- but the viewer
shows it as REJECTED and the exit status is non-zero.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import fitz
import pdfplumber

from core.ir.validate import validate
from core.parser.extract_text import extract_page
from core.parser.layout import page_text
from core.structure.build_ir import build_assemblies

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
LIBRARY = WEB / "library"
MANIFEST = LIBRARY / "index.json"
TMP = ROOT / "data"
PAGE_RENDER_SCALE = 2.0


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "document"


def read_manifest() -> list[dict]:
    if not MANIFEST.exists():
        return []
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def write_manifest(entries: list[dict]) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def run(pdf_path: Path, title: str | None, max_pages: int | None, verbose: bool) -> int:
    if not pdf_path.exists():
        print(f"error: {pdf_path} not found", file=sys.stderr)
        return 2

    doc_id = slugify(pdf_path.stem)
    out_dir = LIBRARY / doc_id
    pages_dir = out_dir / "pages"
    TMP.mkdir(exist_ok=True)
    pages_dir.mkdir(parents=True, exist_ok=True)

    pages: list[dict] = []
    page_words: dict[int, list[dict]] = {}
    page_sizes: dict[int, tuple[float, float]] = {}

    print(f"\n[1/4] extracting text from {pdf_path.name}")
    with pdfplumber.open(str(pdf_path)) as plumber_pdf:
        fitz_doc = fitz.open(str(pdf_path))
        try:
            total = len(plumber_pdf.pages)
            limit = min(total, max_pages) if max_pages else total
            for i in range(limit):
                try:
                    result = extract_page(plumber_pdf, fitz_doc, i, TMP)
                except Exception as e:                      # one bad page never stops a run
                    print(f"      page {i + 1}: failed - {e}")
                    result = {"page": i + 1, "text": "", "tier": None,
                              "confidence": None, "error": str(e)}
                pages.append(result)

                pp = plumber_pdf.pages[i]
                words = pp.extract_words() or []
                page_words[i + 1] = words
                page_sizes[i + 1] = (float(pp.width), float(pp.height))

                # Drop running heads and folios before anything reads the page,
                # and split columns before anything reads a line, otherwise the
                # two columns of a service manual arrive zipped together.
                body = page_text(words, float(pp.width), float(pp.height))
                if body:
                    result["text"] = body

            print(f"      {limit} pages, tiers used: {_tier_summary(pages)}")

            print("[2/4] decoding procedures")
            assemblies = build_assemblies(
                pages=pages,
                title=title or pdf_path.stem.replace("_", " "),
                source_document=pdf_path.name,
                page_words=page_words,
                page_sizes=page_sizes,
            )
            asm = assemblies[0]
            if len(assemblies) == 1:
                print(f"      {len(asm.parts)} parts, {len(asm.steps)} steps")
            else:
                total = sum(len(a.steps) for a in assemblies)
                print(f"      {len(assemblies)} procedures, {total} steps in total")

            if not asm.steps:
                print("\n      No numbered procedure steps were found in this document.")
                print("      The extractor looks for lines like '7. Fit the piston...'.")
                print("      Check the text actually came out: --verbose\n")

            print("[3/4] rendering cited pages")
            cited = sorted({p.page for a in assemblies for _, p in a.provenance_items})
            for page_no in cited:
                _render_page(fitz_doc, page_no - 1, pages_dir)
            print(f"      {len(cited)} page images -> {pages_dir.relative_to(WEB)}")
        finally:
            fitz_doc.close()

    print("[4/4] validating")
    entries = [e for e in read_manifest()
               if e["id"] != doc_id and e.get("document") != doc_id]
    admissible = 0
    for n, a in enumerate(assemblies):
        report = validate(a)
        # One procedure per directory, but page images are shared: every
        # procedure cites the same document and re-rendering per procedure
        # would write the same PNG two hundred times.
        sub_id = doc_id if len(assemblies) == 1 else f"{doc_id}-p{n + 1:03d}"
        sub_dir = LIBRARY / sub_id
        sub_dir.mkdir(parents=True, exist_ok=True)
        a.save(sub_dir / "ir.json")
        (sub_dir / "validation.json").write_text(
            json.dumps(report.to_dict(), indent=2), encoding="utf-8"
        )
        admissible += report.ok
        entries.append(_manifest_entry(sub_id, a, report, pdf_path, len(pages),
                                       doc_id if len(assemblies) > 1 else None))
        if len(assemblies) == 1:
            print(report.render())

    if len(assemblies) > 1:
        print(f"      {admissible}/{len(assemblies)} procedures ADMISSIBLE")
        print(f"      {len(assemblies) - admissible} rejected\n")

    entries.sort(key=lambda e: (e["ingestedAt"], e["id"]), reverse=True)
    write_manifest(entries)
    print(f"  library: {len(assemblies)} entr(y/ies) for {doc_id}"
          f"  ({len(entries)} total indexed)\n")
    report = validate(assemblies[0])

    if verbose:
        for step in asm.steps:
            flag = "ok " if step.provenance and step.provenance.verified else "?? "
            print(f"  {flag} {step.id}  {step.text[:88]}")
        print()

    return 0 if report.ok else 1


def _manifest_entry(sub_id, asm, report, pdf_path, page_count, document):
    """One library card. `document` is the parent doc for a split manual."""
    entry = {
        "id": sub_id,
        "title": asm.title,
        "source": pdf_path.name,
        "pages": page_count,
        "parts": len(asm.parts),
        "steps": len(asm.steps),
        "torqueSpecs": sum(1 for s in asm.steps if s.torque_nm is not None),
        "verifiedSpans": sum(1 for _, p in asm.provenance_items if p.verified),
        "totalSpans": len(asm.parts) + len(asm.steps),
        "ok": report.ok,
        "ingestedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if document:
        # Page images are rendered once per document, not once per procedure.
        entry["document"] = document
    return entry


def _render_page(fitz_doc: fitz.Document, page_index: int, out_dir: Path) -> None:
    page = fitz_doc[page_index]
    pix = page.get_pixmap(matrix=fitz.Matrix(PAGE_RENDER_SCALE, PAGE_RENDER_SCALE))
    pix.save(str(out_dir / f"page_{page_index + 1}.png"))


def _tier_summary(pages: list[dict]) -> str:
    counts: dict[str, int] = {}
    for p in pages:
        k = str(p.get("tier"))
        counts[k] = counts.get(k, 0) + 1
    return ", ".join(f"tier {k}={v}" for k, v in sorted(counts.items()))


def main() -> None:
    ap = argparse.ArgumentParser(description="Decode a technical document into a renderable world.")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--title", default=None, help="title shown in the viewer")
    ap.add_argument("--max-pages", type=int, default=None)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    sys.exit(run(args.pdf, args.title, args.max_pages, args.verbose))


if __name__ == "__main__":
    main()
