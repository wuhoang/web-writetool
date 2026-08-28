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
    unit_col = 1 if len(header) > 1 else None

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


def _token_text(token) -> str:
    """Get token text (works for both Token objects and plain tuples)."""
    if hasattr(token, "text"):
        return token.text
    return str(token)


def map_material_tracking(sections: list[Section], rules: dict) -> tuple[dict, list[str]]:
    """Map page 2 '材料追踪' section.

    Returns (result, notes) where result has:
      - summary: cost summary rows (当日/井段累计/全井累计)
      - engineer_costs: list of engineer cost entries (currently just headers)
      - materials: list of material consumption rows
    """
    cfg = rules.get("material_tracking", {})
    sec = _find_section(sections, cfg.get("match_title", "材料追踪"))
    if sec is None:
        return {}, ["section_not_found:材料追踪"]

    lines = sec.lines
    result: dict = {"summary": {}, "engineer_costs": [], "materials": []}
    notes: list[str] = []

    # Parse summary rows (lines 4-10 area: 工程师费用, 材料费用, 设备费用, etc.)
    # These are short lines: label + 1-3 numeric values (当日/井段累计/全井累计)
    # Distinguish from table header lines which have many label tokens
    summary_labels = set()
    for row_spec in cfg.get("summary_rows", {}).values():
        for alias in row_spec:
            summary_labels.add(alias)

    for ln in lines:
        text = ln.text()
        tokens = ln.tokens
        if len(tokens) < 2 or len(tokens) > 5:
            continue
        first_token = tokens[0].text.strip()
        if first_token not in summary_labels:
            continue
        # Check remaining tokens are numeric (not more labels)
        remaining = [t.text.strip() for t in tokens[1:]]
        non_numeric = sum(1 for r in remaining if _number(r) is None and not r.startswith("¥"))
        if non_numeric > 0:
            continue  # This is a header line, not a summary row
        result["summary"][first_token] = {
            "raw_text": text,
            "values": remaining,
            "confidence": CONF_EXACT,
            "source": {"page": sec.page, "bbox": [ln.x0, ln.y0, ln.x1, ln.y1]},
        }

    # Find material data rows: start after "材料费用" + column header lines
    # Material rows have pattern: material_name [unit] [price] numbers...
    data_started = False
    for ln in lines:
        text = ln.text()
        tokens = ln.tokens
        if not tokens:
            continue

        first = tokens[0].text.strip()

        # Skip headers and summary rows
        if first in ("材料费用", "工程师费用", "设备费用", "筛布", "当日费用合计",
                      "当日税费", "作业者:", "#5", "QHD35-4-5"):
            continue
        if first in ("当日", "井段累计", "全井累计", "数量", "单价",
                      "单位", "单位/单重", "单位单重", "开始数量",
                      "消耗", "累计消耗当日", "来料", "累计来料当日返料累计返料",
                      "库存", "当日费用", "库存和消耗"):
            continue

        # Material data rows: first token is material name (uppercase letters/hyphens)
        # Must have at least 2 tokens (name + something)
        if len(tokens) < 2:
            continue

        # Identify material name (first token, or first two if second is a suffix like "HV", "LV", "H")
        mat_name = first
        idx = 1
        # Multi-part names: "PF-PAC HV", "PF-XC H", "PF-FOL TROL", "PF-BLN 1/2/3"
        if idx < len(tokens):
            second = tokens[idx].text.strip()
            # If second token is short and alphabetic/numeric (not a unit or price)
            if (len(second) <= 6 and not second.startswith("¥")
                and not second.endswith("Kg/SX") and not second.endswith("Kg/DR")
                and not second.replace(".", "").replace(",", "").isdigit()):
                mat_name += " " + second
                idx += 1

        # Remaining tokens: [unit] [price] [start_qty] [daily_cons] [cum_cons] ...
        remaining = tokens[idx:]
        entry: dict = {
            "material": {"raw_text": mat_name, "value": mat_name, "confidence": CONF_EXACT},
            "source": {"page": sec.page, "bbox": [ln.x0, ln.y0, ln.x1, ln.y1]},
        }

        # Parse remaining tokens by pattern
        nums = []
        unit_raw = None
        price_raw = None
        for t in remaining:
            ttxt = t.text.strip()
            if not ttxt:
                continue
            if "Kg/" in ttxt or "kg/" in ttxt:
                unit_raw = ttxt
            elif ttxt.startswith("¥"):
                if price_raw is None:
                    price_raw = ttxt
                # second ¥ is daily_cost at the end
            else:
                nums.append(ttxt)

        if unit_raw:
            entry["unit"] = {"raw_text": unit_raw, "value": unit_raw, "confidence": CONF_EXACT}
        if price_raw:
            entry["unit_price"] = {"raw_text": price_raw, "value": price_raw, "confidence": CONF_EXACT}

        # Map numeric values to fields based on position
        # Expected order: start_qty, daily_consumption, cum_consumption,
        #                 daily_receipt, cum_receipt, daily_return, cum_return, inventory
        num_fields = [
            "start_qty", "daily_consumption", "cum_consumption",
            "daily_receipt", "cum_receipt", "daily_return", "cum_return", "inventory",
        ]
        for i, nval in enumerate(nums):
            if i < len(num_fields):
                entry[num_fields[i]] = {
                    "raw_text": nval,
                    "value": _number(nval) if _number(nval) is not None else nval,
                    "confidence": CONF_NUMERIC_OK if _number(nval) is not None else CONF_EXACT,
                }

        # Last token might be daily_cost (¥ value)
        if remaining and remaining[-1].text.strip().startswith("¥"):
            entry["daily_cost"] = {
                "raw_text": remaining[-1].text.strip(),
                "value": remaining[-1].text.strip(),
                "confidence": CONF_EXACT,
            }

        result["materials"].append(entry)

    return result, notes


def map_fluid_volume_report(sections: list[Section], rules: dict) -> tuple[dict, list[str]]:
    """Map page 3 '钻井液数量日报' section.

    Returns (result, notes) where result has:
      - tanks: list of tank entries (capacity, density, quantity, type, category)
      - total_volume_m3: total volume
      - non_transfer_volume_m3: non-transfer tank volume
      - wellbore: wellbore mud data
      - balance: mud balance data (rows × columns)
    """
    cfg = rules.get("fluid_volume_report", {})
    sec = _find_section(sections, cfg.get("match_title", "钻井液数量日报"))
    if sec is None:
        return {}, ["section_not_found:钻井液数量日报"]

    lines = sec.lines
    result: dict = {"tanks": [], "wellbore": {}, "balance": {}}
    notes: list[str] = []

    for ln in lines:
        text = ln.text()
        tokens = ln.tokens
        if not tokens:
            continue

        first = tokens[0].text.strip()

        # Skip headers and page metadata
        if first in ("#5", "QHD35-4-5", "作业者:", "罐", "容量", "m³", "g/cm³",
                      "Total", "Non", "Trans", "Volume"):
            continue
        if first in ("钻井液类型", "池类别", "总体积", "不可转移罐体积m³",
                      "井筒内泥浆(m³)", "环空", "管柱", "钻头下", "合计",
                      "钻井液平衡(m³)", "损耗量(m³)", "增/减:", "循环", "储备", "其它",
                      "地层漏失", "地面损耗"):
            continue
        if first.startswith("3 /") or first.startswith("2 /") or first.startswith("1 /"):
            continue

        # Tank data rows: tank_number capacity density quantity type category [total_vol]
        # Use x-coordinate ranges to map columns (density column is often empty)
        # Column x-ranges (from header analysis):
        #   tank_no: <80, capacity: 100-165, density: 165-220, quantity: 220-275,
        #   mud_type: 275-345, pit_category: 345-420, total: >420
        if first.isdigit() and len(tokens) >= 4:
            tank_num = first
            entry = {
                "tank_no": {"raw_text": tank_num, "value": int(tank_num), "confidence": CONF_EXACT},
                "source": {"page": sec.page, "bbox": [ln.x0, ln.y0, ln.x1, ln.y1]},
            }
            # Map tokens by x-coordinate ranges
            # Column ranges: capacity <165, density 165-220, quantity 220-275,
            #                mud_type 275-345, pit_category 345-420, total >420
            mud_buf: list[str] = []
            cat_buf: list[str] = []
            for t in tokens[1:]:
                ttxt = t.text.strip()
                tcx = (t.x0 + t.x1) / 2
                if _number(ttxt) is not None:
                    num = _number(ttxt)
                    if tcx < 165:
                        entry["capacity_m3"] = {"raw_text": ttxt, "value": num, "confidence": CONF_NUMERIC_OK}
                    elif tcx < 220:
                        entry["density_gcm3"] = {"raw_text": ttxt, "value": num, "confidence": CONF_NUMERIC_OK}
                    elif tcx < 275:
                        entry["quantity_m3"] = {"raw_text": ttxt, "value": num, "confidence": CONF_NUMERIC_OK}
                    elif tcx > 420:
                        entry["total_m3"] = {"raw_text": ttxt, "value": num, "confidence": CONF_NUMERIC_OK}
                else:
                    if ttxt:
                        if tcx < 345:
                            mud_buf.append(ttxt)
                        else:
                            cat_buf.append(ttxt)
            if mud_buf:
                merged = "".join(mud_buf)
                entry["mud_type"] = {"raw_text": merged, "value": merged, "confidence": CONF_EXACT}
            if cat_buf:
                merged = "".join(cat_buf)
                entry["pit_category"] = {"raw_text": merged, "value": merged, "confidence": CONF_EXACT}

            result["tanks"].append(entry)
            continue

        # 沉砂 row
        if first == "沉砂":
            nums = [_number(t.text.strip()) for t in tokens[1:] if _number(t.text.strip()) is not None]
            texts = [t.text.strip() for t in tokens[1:] if t.text.strip() and _number(t.text.strip()) is None]
            entry = {
                "tank_no": {"raw_text": "沉砂", "value": "沉砂", "confidence": CONF_EXACT},
                "source": {"page": sec.page, "bbox": [ln.x0, ln.y0, ln.x1, ln.y1]},
            }
            if nums:
                entry["quantity_m3"] = {"raw_text": str(nums[0]), "value": nums[0], "confidence": CONF_NUMERIC_OK}
            if texts:
                entry["mud_type"] = {"raw_text": texts[0], "value": texts[0], "confidence": CONF_EXACT}
            result["tanks"].append(entry)
            continue

        # 总体积 row (e.g. "总体积m³" header or value)
        if "总体积" in first:
            # This might be a header row or a value row
            continue

        # 不可转移罐体积
        if "不可转移" in first:
            continue

        # Wellbore rows: 总井眼量, 非泥浆体积, 钻井液数量
        wellbore_labels = cfg.get("wellbore_rows", {})
        matched_wellbore = False
        for field_id, aliases in wellbore_labels.items():
            if any(alias in first for alias in aliases):
                nums = [t.text.strip() for t in tokens[1:]]
                result["wellbore"][field_id] = {
                    "raw_text": text,
                    "values": nums,
                    "confidence": CONF_NUMERIC_OK,
                    "source": {"page": sec.page, "bbox": [ln.x0, ln.y0, ln.x1, ln.y1]},
                }
                matched_wellbore = True
                break
        if matched_wellbore:
            continue

        # Balance rows (match by containment to handle parentheses like "总体积增量(配浆量)")
        balance_labels = cfg.get("balance_rows", {})
        for field_id, aliases in balance_labels.items():
            if any(alias in first for alias in aliases):
                nums = [t.text.strip() for t in tokens[1:]]
                result["balance"][field_id] = {
                    "raw_text": text,
                    "values": nums,
                    "confidence": CONF_NUMERIC_OK,
                    "source": {"page": sec.page, "bbox": [ln.x0, ln.y0, ln.x1, ln.y1]},
                }
                break

    return result, notes


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
    material_tracking, mt_notes = map_material_tracking(sections, rules)
    fluid_volume, fv_notes = map_fluid_volume_report(sections, rules)

    model = {
        "report_type": rules["document_type"],
        "source_file": pdf_path.name,
        "meta": meta,
        "fluid_properties": fluid,
        "materials_consumed": materials,
        "solids_control": solids,
        "narratives": narratives,
        "material_tracking": material_tracking,
        "fluid_volume_report": fluid_volume,
    }
    audit = {
        "meta": meta_audit,
        "fluid_properties_notes": fluid_notes,
        "material_tracking_notes": mt_notes,
        "fluid_volume_notes": fv_notes,
        "counts": {
            "meta_matched": len(meta),
            "meta_expected": len(rules["meta_fields"]),
            "sample_points": len(fluid),
            "material_rows": len(materials),
            "solids_rows": len(solids),
            "narratives": [k for k, v in narratives.items() if "raw_text" in v],
            "material_tracking_materials": len(material_tracking.get("materials", [])),
            "fluid_volume_tanks": len(fluid_volume.get("tanks", [])),
        },
    }
    return model, audit
