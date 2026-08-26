"""Final spot-check of business_model.json (review aid)."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
m = json.loads((HERE / "output" / "business_model.json").read_text(encoding="utf-8"))

lines = []
n = m["narratives"]
lines.append(f"ENG : {n['engineering_summary']['raw_text']!r}")
lines.append(f"TREAT: {n['treatment_log']['raw_text']!r}")
fp = m["fluid_properties"]["#2"]
for k in ("density_gcm3", "funnel_viscosity_s", "api_filtration_ml", "sampling_time"):
    v = fp.get(k, {})
    lines.append(f"{k}: raw={v.get('raw_text')!r} val={v.get('value')} unit={v.get('unit')}")
mat = m["materials_consumed"][5]
lines.append(f"material[5]: { {k: v['raw_text'] for k, v in mat.items()} }")
sc = m["solids_control"][0]
lines.append(f"solid[0]: { {k: v['raw_text'] for k, v in sc.items()} }")
meta = m["meta"]
for k in ("well_name", "fsr_no", "report_date", "measured_depth", "fluid_type"):
    lines.append(f"{k} -> {meta[k]['raw_text']!r} | src: {meta[k]['source']}")

out = "\n".join(lines)
print(out)
(HERE / "output" / "check_model.txt").write_text(out, encoding="utf-8")
