"""Debug: where do specific tokens land?"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yaml

from layout_recovery import extract_page_lines, find_title_tokens, split_content_by_sections
import pymupdf

ROOT = Path(__file__).resolve().parent.parent
rules = yaml.safe_load((ROOT / "config" / "field_rules.yaml").read_text(encoding="utf-8"))
bounds = rules.get("layout_hints", {}).get("same_row_boundaries", {})

doc = pymupdf.open(ROOT / "report_data.pdf")
page = doc[0]
lines = extract_page_lines(page, 1)
pairs = find_title_tokens(lines, set(rules["section_titles"]))
sections, pool = split_content_by_sections(lines, pairs, bounds)

Y_MIN, Y_MAX = float(sys.argv[1]) if len(sys.argv) > 1 else 205, float(sys.argv[2]) if len(sys.argv) > 2 else 310

print("== title tokens ==")
for tk, name in pairs:
    print(f"  {name:10s} y={tk.y0:.1f} x={tk.x0:.1f}-{tk.x1:.1f}")

print(f"== token ownership y∈[{Y_MIN},{Y_MAX}] ==")
for sec in sections:
    for ln in sec.lines:
        for tk in ln.tokens:
            if Y_MIN <= tk.y0 <= Y_MAX and (tk.x0 > 395 or Y_MAX < 400):
                print(f"  [{sec.title}] y={tk.y0:.1f} x={tk.x0:.1f}-{tk.x1:.1f} | {tk.text!r}")
                break
