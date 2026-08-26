"""POC-1 orchestrator: report_data.pdf -> document structure + business model.

Outputs (poc/output/):
  document_structure.json   intermediate structure recovery result
  business_model.json       Business Data Model per design doc section 5.1
  poc1_report.txt           human-readable verification report
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from field_mapping import build_business_model
from layout_recovery import detect_column_bands, extract_key_values, extract_table, parse_document

ROOT = Path(__file__).resolve().parent.parent
PDF_PATH = ROOT / "report_data.pdf"
RULES_PATH = ROOT / "config" / "field_rules.yaml"
OUT_DIR = Path(__file__).resolve().parent / "output"


def _section_json(sec) -> dict:
    info = {"title": sec.title, "page": sec.page, "line_count": len(sec.lines)}
    table_like = sec.title not in ("工程作业简况", "钻井液处理与维护")
    if table_like and sec.lines:
        bands = detect_column_bands(sec.lines)
        table = extract_table(sec)
        info["column_bands"] = [[round(a, 1), round(b, 1)] for a, b in bands]
        info["header"] = table["header"]
        info["data_rows"] = table["data"]
    else:
        info["lines"] = [ln.text() for ln in sec.lines]
    return info


def main() -> int:
    if not PDF_PATH.exists():
        print(f"missing input: {PDF_PATH}")
        return 1
    OUT_DIR.mkdir(exist_ok=True)

    rules_stub = None
    import yaml

    rules_stub = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))

    hints = rules_stub.get("layout_hints", {})
    boundaries = hints.get("same_row_boundaries", {})
    xbands = {k: tuple(v) for k, v in hints.get("section_xbands", {}).items()}
    doc = parse_document(PDF_PATH, set(rules_stub["section_titles"]), boundaries, xbands)
    structure_out = {
        "pages": doc["pages"],
        "sections": [_section_json(s) for s in doc["sections"]],
        "header_kv": [
            {"label": kv.label, "raw_text": kv.raw_text, "page": kv.page,
             "bbox": [round(v, 1) for v in kv.bbox]}
            for kv in doc["header_kv"]
        ],
    }
    (OUT_DIR / "document_structure.json").write_text(
        json.dumps(structure_out, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    model, audit = build_business_model(PDF_PATH, RULES_PATH)
    (OUT_DIR / "business_model.json").write_text(
        json.dumps(model, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    lines: list[str] = []
    ap = lines.append
    ap("POC-1 验证报告 — report_data.pdf 结构恢复与字段映射")
    ap("=" * 60)
    ap("")
    ap("[页面]")
    for p in doc["pages"]:
        ap(f"  第{p['page']}页: {p['width']}x{p['height']}, 视觉行 {p['line_count']}")
    ap("")
    ap("[节区识别]")
    for sj in structure_out["sections"]:
        extra = f", 表头={sj['header']}" if "header" in sj else ""
        ap(f"  '{sj['title']}' (第{sj['page']}页, 行数={len(sj.get('lines', sj.get('data_rows', [])))}){extra}")
    ap("")
    ap("[表单键值对] (页眉区域)")
    for kv in structure_out["header_kv"]:
        ap(f"  {kv['label']:12s} = {kv['raw_text']!r}  (第{kv['page']}页)")
    ap("")
    ap("[meta 字段映射]")
    ca = audit["counts"]
    ap(f"  命中 {ca['meta_matched']}/{ca['meta_expected']}")
    if audit["meta"]["missing"]:
        ap(f"  缺失: {audit['meta']['missing']}")
    unmapped = audit["meta"]["unmapped_kv_labels"]
    if unmapped:
        ap(f"  未消费的KV标签: {unmapped}")
    ap("")
    ap("[钻井液性能表]")
    ap(f"  取样点数: {ca['sample_points']}")
    fp = model["fluid_properties"]
    if fp:
        first = next(iter(fp))
        fields_n = sorted(fp[first])
        ap(f"  每点字段数: {len(fields_n)} -> {fields_n[:8]}{'...' if len(fields_n) > 8 else ''}")
        dens = fp[first].get("density_gcm3")
        filt = fp[first].get("api_filtration_ml")
        if dens:
            ap(f"  密度示例[{first}]: raw={dens['raw_text']!r} value={dens.get('value')} unit={dens.get('unit')}")
        if filt:
            ap(f"  失水示例[{first}]: raw={filt['raw_text']!r} value={filt.get('value')}")
    if audit["fluid_properties_notes"]:
        ap(f"  未识别行标签: {audit['fluid_properties_notes']}")
    ap("")
    ap(f"[当日材料] 行数: {ca['material_rows']}")
    for row in model["materials_consumed"][:4]:
        code = row.get("code", {}).get("raw_text")
        qty = row.get("quantity", {})
        ap(f"  {code}: {qty.get('raw_text')!r}")
    if len(model["materials_consumed"]) > 4:
        ap(f"  ... 共{len(model['materials_consumed'])}行")
    ap("")
    ap(f"[固控设备] 行数: {ca['solids_rows']}")
    ap("")
    ap("[长文本段落] (原文保真)")
    for nid in audit["counts"]["narratives"]:
        text = model["narratives"][nid]["raw_text"]
        preview = text.replace("\n", "\\n")[:80]
        ap(f"  {nid}: {len(text)}字 | {preview}...")
    missing_narr = set(rules_stub["narrative_sections"]) - set(ca["narratives"])
    if missing_narr:
        ap(f"  缺失段落: {sorted(missing_narr)}")
    ap("")
    ap("输出文件: document_structure.json / business_model.json / poc1_report.txt")

    report = "\n".join(lines)
    (OUT_DIR / "poc1_report.txt").write_text(report, encoding="utf-8")
    try:
        print(report)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(report.encode("utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
