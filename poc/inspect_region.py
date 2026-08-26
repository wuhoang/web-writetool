"""POC-1 Step 1b: inspect word coordinates of a page region (debug aid)."""
import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent / "output" / "explore_words.json"


def main() -> None:
    pno = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    y_min = float(sys.argv[2]) if len(sys.argv) > 2 else 0
    y_max = float(sys.argv[3]) if len(sys.argv) > 3 else 10**9

    data = json.loads(OUT.read_text(encoding="utf-8"))
    words = data["pages"][pno - 1]["words"]
    selected = [w for w in words if y_min <= w["bbox"][1] <= y_max]
    selected.sort(key=lambda w: (round(w["bbox"][1], 0), w["bbox"][0]))
    for w in selected:
        b = w["bbox"]
        print(f"y={b[1]:6.1f}-{b[3]:6.1f} x={b[0]:6.1f}-{b[2]:6.1f} blk={w['block']:2d} ln={w['line']:2d} | {w['text']}")


if __name__ == "__main__":
    main()
