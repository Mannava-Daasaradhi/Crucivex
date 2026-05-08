import pdfplumber
import sys
import base64
import requests
import hashlib
import fitz
import pytesseract
from PIL import Image


def render_page_image(pdf_path, page_num):
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    mat = fitz.Matrix(2, 2)
    pix = page.get_pixmap(matrix=mat)
    img_path = f"data/page_{page_num+1}.png"
    pix.save(img_path)
    return img_path


def extract_text_with_tesseract(img_path):
    data = pytesseract.image_to_data(Image.open(img_path), output_type=pytesseract.Output.DICT)
    confidences = [int(c) for c in data['conf'] if c != '-1']
    text = ' '.join(w for w, c in zip(data['text'], data['conf']) if c != '-1' and int(c) > 0)
    mean_conf = sum(confidences) / len(confidences) if confidences else 0
    return text, mean_conf


def extract_text_with_vision(img_path):
    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()
    response = requests.post("http://localhost:11434/api/generate", json={
        "model": "moondream",
        "prompt": "Extract all text from this image exactly as written. No commentary. No formatting. Just the text.",
        "images": [img_b64],
        "stream": False
    })
    result = response.json()
    return result.get("response", "[no response]")


def extract_page(pdf_path, page_num):
    import os
    os.makedirs("data", exist_ok=True)
    
    # Tier 1: pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        text = pdf.pages[page_num].extract_text() or ""
    if len(text.strip()) > 50:
        return text

    # Tier 2: tesseract
    img_path = render_page_image(pdf_path, page_num)
    text, conf = extract_text_with_tesseract(img_path)
    print(f"  tesseract conf: {conf:.1f}")
    if conf >= 60:
        return text

    # Tier 3: moondream
    return extract_text_with_vision(img_path)


def extract_text(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        num_pages = len(pdf.pages)
    for i in range(num_pages):
        print(f"\n--- Page {i+1} ---")
        text = extract_page(pdf_path, i)
        print(deduplicate(text))


def deduplicate(text):
    seen = set()
    result = []
    for block in text.split('\n\n'):
        h = hashlib.md5(block.strip().encode()).hexdigest()
        if h not in seen:
            seen.add(h)
            result.append(block)
    return '\n\n'.join(result)

if __name__ == "__main__":
    extract_text(sys.argv[1])