"""Business field mapping: recovered document structure -> Business Data Model.

Consumes Section/KeyValue objects produced by layout_recovery and the alias
rules from config/field_rules.yaml. Every mapped value keeps raw_text plus
source provenance; natural language fields are never rewritten (design doc
section 5.3 hard rule).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from layout_recovery import KeyValue, Line, Section, parse_document

CONF_EXACT = 0.99
CONF_NUMERIC_OK = 0.97
CONF_PARAGRAPH = 1.0


@dataclass
class MappedValue:
    field_id: str
    raw_text: str
    value: object
    confidence: float
    source: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "raw_text": self.raw_text,
            "value": self.value,
            "confidence": self.confidence,
            "source": self.source,
            **({"warnings": self.warnings} if self.warnings else {}),
        }


def load_rules(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _number(text: str) -> float | None:
    m = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    return float(m.group()) if m else None


def _norm_label(label: str) -> str:
    return re.sub(r"\s+", "", label)


def _apply_transforms(raw: str, transforms: list[str]) -> str:
    out = raw
    for t in transforms:
        if t == "collapse_spaces":
            out = re.sub(r"\s+", "", out)
        elif t == "slash_first":
            out = out.split("/")[0].strip()
    return out


def map_meta_fields(kv_pairs: list[KeyValue], rules: dict) -> tuple[dict, dict]:
    meta: dict[str, MappedValue] = {}
    used_pairs: set[int] = set()
    for field_id, spec in rules["meta_fields"].items():
        if "derive_from" in spec:
            continue
        aliases = {_norm_label(a) for a in spec["aliases"]}
        for idx, kv in enumerate(kv_pairs):
            if idx in used_pairs:
                continue
            if _norm_label(kv.label) not in aliases:
                continue
            used_pairs.add(idx)
            raw = kv.raw_text.strip()
            warnings: list[str] = []
            ftype = spec.get("type", "string")
            value: object = raw
            kv_raw_original = raw
            if "transforms" in spec and ftype == "string":
                raw = _apply_transforms(raw, spec["transforms"])
                value = raw
            if ftype == "number":
                num = _number(raw)
                if num is None:
                    warnings.append("numeric_parse_failed")
                else:
                    value, raw = num, raw
                    lo, hi = spec.get("range", [-10**9, 10**9])
                    if not lo <= num <= hi:
                        warnings.append("out_of_range")
            elif ftype == "depth_pair":
                nums = re.findall(r"\d+(?:\.\d+)?", raw)
                value = {"td_m": float(nums[0]) if len(nums) > 0 else None,
                         "tvd_m": float(nums[1]) if len(nums) > 1 else None}
            conf = CONF_EXACT if not warnings else CONF_NUMERIC_OK
            src = {"page": kv.page, "bbox": [round(v, 1) for v in kv.bbox]}
            if "transforms" in spec and ftype == "string":
                src["kv_raw"] = kv_raw_original
            meta[field_id] = MappedValue(
                field_id=field_id,
                raw_text=raw,
                value=value,
                confidence=conf,
                source=src,
                warnings=warnings,
            )
            break

    for field_id, spec in rules["meta_fields"].items():
        if "derive_from" not in spec or spec["derive_from"] not in meta:
            continue
        origin = meta[spec["derive_from"]].source.get("kv_raw", "")
        m = re.search(spec["derive_pattern"], origin)
        if m:
            meta[field_id] = MappedValue(
                field_id=field_id,
                raw_text=m.group(1),
                value=m.group(1),
                confidence=0.9,
                source={"derived_from": spec["derive_from"], "pattern": spec["derive_pattern"]},
            )

    audit = {
        "matched": sorted(meta),
        "missing": sorted(set(rules["meta_fields"]) - set(meta)),
        "unmapped_kv_labels": [kv.label for i, kv in enumerate(kv_pairs) if i not in used_pairs],
    }
    return {k: v.to_json() for k, v in meta.items()}, audit


def _find_section(sections: list[Section], title: str) -> Section | None:
    target = title.replace(" ", "")
    for s in sections:
        if s.title.replace(" ", "") == target:
            return s
    return None


TIME_VALUE_RE = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")


def map_fluid_properties(sections: list[Section], rules: dict) -> tuple[dict, list[str]]:
    profile = rules["fluid_properties"]
    sec = _find_section(sections, profile["match_title"])
    if sec is None:
        return {}, [f"section_not_found:{profile['match_title']}"]
    table = _table_of(sec)
    header = table["header"]
    col_map: dict[int, str] = {}
    for band_idx, cell in enumerate(header):
        name = cell.replace(" ", "")
        if name in profile["sample_columns"]:
            col_map[band_idx] = name
    label_col = 0
    unit_col = 1 if len(header) > max(col_map, default=0) else None

    alias_to_field: dict[str, str] = {}
    for fid, aliases in profile["row_aliases"].items():
        for a in aliases:
            alias_to_field[_norm_label(a)] = fid

    samples: dict[str, dict] = {name: {} for name in profile["sample_columns"]}
    notes: list[str] = []
    for row in table["data"]:
        label = _norm_label(row[label_col])
        fid = alias_to_field.get(label)
        if fid is None:
            if label:
                notes.append(f"unmapped_row_label:{label}")
            continue
        unit = row[unit_col] if unit_col is not None and unit_col < len(row) else ""
        for band_idx, sample_name in col_map.items():
            if band_idx >= len(row):
                continue
            cell_raw = row[band_idx].strip()
            if not cell_raw:
                continue
            entry: dict = {"raw_text": cell_raw, "unit": unit or None}
            if "/" in cell_raw or TIME_VALUE_RE.match(cell_raw):
                entry["value"] = cell_raw
            elif (num := _number(cell_raw)) is not None:
                entry["value"] = num
                rng = profile.get("numeric_ranges", {}).get(fid)
                if rng and not rng[0] <= num <= rng[1]:
                    entry["warnings"] = ["out_of_range"]
                entry["confidence"] = CONF_NUMERIC_OK
            else:
                entry["value"] = cell_raw
            if "confidence" not in entry:
                entry["confidence"] = CONF_EXACT
            entry["source"] = {"page": sec.page, "row_label": row[label_col], "column": sample_name}
            samples[sample_name][fid] = entry
    return samples, notes


def _table_of(sec: Section) -> dict:
    from layout_recovery import extract_table

    return extract_table(sec)


def map_simple_table(
    sections: list[Section],
    match_title: str,
    columns: dict,
    required_key: str | None = None,
) -> tuple[list[dict], list[str]]:
    sec = _find_section(sections, match_title)
    if sec is None:
        return [], [f"section_not_found:{match_title}"]
    table = _table_of(sec)
    header = [_norm_label(c) for c in table["header"]]
    col_index: dict[str, int] = {}
    for out_name, aliases in columns.items():
        for i, hname in enumerate(header):
            if hname in {_norm_label(a) for a in aliases}:
                col_index[out_name] = i
                break
    rows_out: list[dict] = []
    for row in table["data"]:
        item: dict = {}
        for out_name, idx in col_index.items():
            raw = row[idx].strip() if idx < len(row) else ""
            if not raw:
                continue
            val: object = raw
            if out_name in ("quantity", "hours"):
                num = _number(raw)
                val = num if num is not None else raw
            item[out_name] = {"raw_text": raw, "value": val, "confidence": CONF_EXACT}
        if item and (required_key is None or required_key in item):
            rows_out.append(item)
    return rows_out, []


_SENTENCE_END = "。；！？.!?"


def join_paragraph(lines: list[Line]) -> tuple[str, list[str]]:
    raw_lines = [ln.text() for ln in lines if ln.text()]
    joined = ""
    for seg in raw_lines:
        if not joined:
            joined = seg
        elif joined[-1] in _SENTENCE_END:
            joined += "\n" + seg
        else:
            joined += seg
    return joined.strip(), raw_lines


def map_narratives(sections: list[Section], rules: dict) -> dict:
    stop_patterns = rules.get("narrative_stop_patterns", [])
    out: dict[str, dict] = {}
    for field_id, title in rules["narrative_sections"].items():
        sec = _find_section(sections, title)
        if sec is None:
            out[field_id] = {"error": f"section_not_found:{title}"}
            continue
        kept: list[Line] = []
        for ln in sec.lines:
            text = ln.text()
            if any(p in text for p in stop_patterns):
                break
            kept.append(ln)
        text, raw_lines = join_paragraph(kept)
        out[field_id] = {
            "raw_text": text,
            "raw_lines": raw_lines,
            "confidence": CONF_PARAGRAPH,
            "source": {
                "page": sec.page,
                "line_count": len(raw_lines),
                "bbox": [
                    round(sec.title_bbox[0], 1),
                    round(min((ln.y0 for ln in sec.lines), default=sec.title_bbox[1]), 1),
                    round(max((ln.x1 for ln in sec.lines), default=sec.title_bbox[2]), 1),
                    round(max((ln.y1 for ln in sec.lines), default=sec.title_bbox[3]), 1),
                ],
            },
        }
    return out


def build_business_model(pdf_path: Path, rules_path: Path) -> tuple[dict, dict]:
    rules = load_rules(rules_path)
    hints = rules.get("layout_hints", {})
    boundaries = hints.get("same_row_boundaries", {})
    xbands = {k: tuple(v) for k, v in hints.get("section_xbands", {}).items()}
    doc = parse_document(pdf_path, set(rules["section_titles"]), boundaries, xbands)
    sections: list[Section] = doc["sections"]

    meta, meta_audit = map_meta_fields(doc["header_kv"], rules)
    fluid, fluid_notes = map_fluid_properties(sections, rules)
    materials, _ = map_simple_table(
        sections,
        rules["materials_table"]["match_title"],
        rules["materials_table"]["columns"],
        required_key="code",
    )
    solids, _ = map_simple_table(
        sections,
        rules["solids_control_table"]["match_title"],
        rules["solids_control_table"]["columns"],
        required_key="equipment",
    )
    narratives = map_narratives(sections, rules)

    model = {
        "report_type": rules["document_type"],
        "source_file": pdf_path.name,
        "meta": meta,
        "fluid_properties": fluid,
        "materials_consumed": materials,
        "solids_control": solids,
        "narratives": narratives,
    }
    audit = {
        "meta": meta_audit,
        "fluid_properties_notes": fluid_notes,
        "counts": {
            "meta_matched": len(meta),
            "meta_expected": len(rules["meta_fields"]),
            "sample_points": len(fluid),
            "material_rows": len(materials),
            "solids_rows": len(solids),
            "narratives": [k for k, v in narratives.items() if "raw_text" in v],
        },
    }
    return model, audit
