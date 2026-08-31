"""批量测试 POC-1 提取：扫描 data/ 下所有 PDF，逐个提取并汇总结果。"""
from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from field_mapping import build_business_model
from layout_recovery import detect_column_bands, extract_table, parse_document

ROOT = Path(__file__).resolve().parent.parent
RULES_PATH = ROOT / "config" / "field_rules.yaml"
DATA_DIR = ROOT / "data"


def extract_one(pdf_path: Path, rules: dict) -> dict:
    """对单个 PDF 执行提取，返回结构化结果。"""
    hints = rules.get("layout_hints", {})
    boundaries = hints.get("same_row_boundaries", {})
    xbands = {k: tuple(v) for k, v in hints.get("section_xbands", {}).items()}

    doc = parse_document(pdf_path, set(rules["section_titles"]), boundaries, xbands)
    model, audit = build_business_model(pdf_path, RULES_PATH)

    ca = audit["counts"]
    return {
        "file": pdf_path.name,
        "pages": len(doc["pages"]),
        "sections": len(doc["sections"]),
        "meta_hit": f"{ca['meta_matched']}/{ca['meta_expected']}",
        "meta_missing": audit["meta"]["missing"],
        "sample_points": ca["sample_points"],
        "fields_per_point": len(next(iter(model["fluid_properties"].values()))) if model["fluid_properties"] else 0,
        "material_rows": ca["material_rows"],
        "solids_rows": ca["solids_rows"],
        "narratives": list(ca["narratives"]),
        "narrative_missing": sorted(set(rules.get("narrative_sections", [])) - set(ca["narratives"])),
        "ok": not audit["meta"]["missing"],
    }


def main():
    if not DATA_DIR.exists():
        print(f"数据目录不存在: {DATA_DIR}")
        return 1

    pdfs = sorted(DATA_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"data/ 下没有 PDF 文件")
        return 1

    rules = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))

    print(f"批量测试 POC-1 提取 — {len(pdfs)} 个 PDF")
    print("=" * 70)

    results = []
    for i, pdf in enumerate(pdfs, 1):
        t0 = time.time()
        try:
            r = extract_one(pdf, rules)
            r["elapsed"] = f"{time.time() - t0:.1f}s"
            r["error"] = None
        except Exception as e:
            r = {
                "file": pdf.name, "ok": False, "error": str(e),
                "elapsed": f"{time.time() - t0:.1f}s",
            }
        results.append(r)

        # 实时输出
        status = "OK" if r.get("ok") else ("ERR" if r.get("error") else "PARTIAL")
        meta = r.get("meta_hit", "N/A")
        err = f" [{r['error'][:60]}]" if r.get("error") else ""
        miss = ""
        if r.get("meta_missing"):
            miss = f" 缺: {r['meta_missing'][:3]}"
        print(f"  [{status}] {r['file']:<50s} meta={meta}{miss}{err}  ({r['elapsed']})")

    # 汇总
    print(f"\n{'=' * 70}")
    ok_count = sum(1 for r in results if r.get("ok"))
    partial = sum(1 for r in results if not r.get("ok") and not r.get("error"))
    err_count = sum(1 for r in results if r.get("error"))
    print(f"总计: {ok_count} 完全命中 / {partial} 部分命中 / {err_count} 异常 / {len(results)} 总数")

    if partial > 0 or err_count > 0:
        print("\n未完全命中的文件:")
        for r in results:
            if not r.get("ok"):
                reason = r.get("error") or f"meta={r.get('meta_hit','?')} missing={r.get('meta_missing',[])}"
                print(f"  {r['file']}: {reason}")

    # 保存完整结果
    out = DATA_DIR / "batch_test_results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n详细结果已保存: {out}")

    return 0 if ok_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
