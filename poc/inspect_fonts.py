"""POC-1 Step 1c: inspect span fonts/sizes (debug aid)."""
from pathlib import Path

import pymupdf

PDF_PATH = Path(__file__).resolve().parent.parent / "report_data.pdf"


def main() -> None:
    doc = pymupdf.open(PDF_PATH)
    page = doc[0]
    seen = {}
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                key = (span["font"], round(span["size"], 1))
                seen.setdefault(key, []).append(span["text"])
    for (font, size), texts in sorted(seen.items(), key=lambda kv: -kv[0][1]):
        sample = " | ".join(texts[:6])
        print(f"size={size:5.1f} font={font:30s} n={len(texts):3d}  {sample}")


if __name__ == "__main__":
    main()
