"""POC-1 Step 1: dump raw words/blocks of report_data.pdf for layout inspection."""
import json
import sys
from pathlib import Path

import pymupdf

PDF_PATH = Path(__file__).resolve().parent.parent / "report_data.pdf"
OUT_PATH = Path(__file__).resolve().parent / "output" / "explore_words.json"


def main() -> None:
    doc = pymupdf.open(PDF_PATH)
    summary = {
        "page_count": len(doc),
        "pages": [],
    }
    for pno, page in enumerate(doc):
        words = page.get_text("words")  # x0, y0, x1, y1, text, block, line, word_no
        blocks = page.get_text("blocks")
        page_dir = {
            "page": pno + 1,
            "width": round(page.rect.width, 1),
            "height": round(page.rect.height, 1),
            "word_count": len(words),
            "block_count": len(blocks),
            "words": [
                {
                    "bbox": [round(w[0], 1), round(w[1], 1), round(w[2], 1), round(w[3], 1)],
                    "text": w[4],
                    "block": w[5],
                    "line": w[6],
                }
                for w in words
            ],
        }
        summary["pages"].append(page_dir)

    OUT_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"pages={summary['page_count']}")
    for p in summary["pages"]:
        print(f"page {p['page']}: {p['width']}x{p['height']}, words={p['word_count']}, blocks={p['block_count']}")

    plain = "\n\n".join(f"===== PAGE {i+1} =====\n{doc[i].get_text('text')}" for i in range(len(doc)))
    (OUT_PATH.parent / "explore_plain.txt").write_text(plain, encoding="utf-8")
    print("written:", OUT_PATH)


if __name__ == "__main__":
    sys.exit(main())
