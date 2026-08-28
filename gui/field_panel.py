"""Field verification panel: Treeview display + inline edit + PDF highlight callback.

Displays business_model fields grouped by section, with confidence color coding.
Click a row to highlight its source region on the PDF viewer.
Double-click to edit the value.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

# Confidence → tag name for color coding
CONF_TAGS = [
    (1.0, "conf_100", "#2e7d32"),   # green  — paragraph/derived
    (0.99, "conf_099", "#1565c0"),  # blue   — exact match
    (0.97, "conf_097", "#f9a825"),  # yellow — numeric parse OK
    (0.90, "conf_090", "#e65100"),  # orange — derived/low
]

WARN_TAG = "conf_warn"


class FieldPanel(ttk.Frame):
    """Right panel: grouped Treeview of all business fields."""

    def __init__(self, master: tk.Widget, on_highlight: Callable[[list[float], int], None] | None = None):
        super().__init__(master)
        self._on_highlight = on_highlight
        self._model: dict = {}
        self._edited: dict[str, str] = {}  # field_key → user-edited value
        self._build_ui()

    def _build_ui(self):
        # Treeview with scrollbar
        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True)

        columns = ("value", "confidence", "page", "status")
        self._tree = ttk.Treeview(
            container, columns=columns, show="tree headings", selectmode="browse",
        )
        self._tree.heading("#0", text="字段")
        self._tree.heading("value", text="提取值")
        self._tree.heading("confidence", text="置信度")
        self._tree.heading("page", text="页")
        self._tree.heading("status", text="状态")

        self._tree.column("#0", width=160, minwidth=120)
        self._tree.column("value", width=200, minwidth=100)
        self._tree.column("confidence", width=60, minwidth=50, anchor=tk.CENTER)
        self._tree.column("page", width=35, minwidth=30, anchor=tk.CENTER)
        self._tree.column("status", width=60, minwidth=50, anchor=tk.CENTER)

        vsb = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # Color tags
        for _, tag, color in CONF_TAGS:
            self._tree.tag_configure(tag, foreground=color)
        self._tree.tag_configure(WARN_TAG, foreground="red", font=("", 9, "bold"))

        # Bindings
        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree.bind("<Double-1>", self._on_double_click)

        # Edit frame (hidden by default)
        self._edit_frame = ttk.Frame(self)
        self._edit_label = ttk.Label(self._edit_frame, text="编辑值:")
        self._edit_label.pack(side=tk.LEFT, padx=(0, 4))
        self._edit_var = tk.StringVar()
        self._edit_entry = ttk.Entry(self._edit_frame, textvariable=self._edit_var, width=40)
        self._edit_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._edit_btn_ok = ttk.Button(self._edit_frame, text="确认", command=self._confirm_edit)
        self._edit_btn_ok.pack(side=tk.LEFT, padx=4)
        self._edit_btn_cancel = ttk.Button(self._edit_frame, text="取消", command=self._cancel_edit)
        self._edit_btn_cancel.pack(side=tk.LEFT)
        # Don't pack _edit_frame yet — shown on double-click

        self._editing_iid: str | None = None

    # ── Public API ─────────────────────────────────────────

    def load_model(self, model: dict):
        """Parse business_model dict and populate the Treeview."""
        self._model = model
        self._edited.clear()
        self._tree.delete(*self._tree.get_children())

        # Group 1: Meta fields
        meta = model.get("meta", {})
        if meta:
            grp = self._tree.insert("", tk.END, text="基本信息", open=True, values=("", "", "", ""))
            for fid, entry in sorted(meta.items()):
                if isinstance(entry, dict) and "raw_text" in entry:
                    self._insert_field(grp, fid, entry)

        # Group 2: Fluid properties
        fp = model.get("fluid_properties", {})
        if fp:
            grp = self._tree.insert("", tk.END, text="钻井液性能", open=False, values=("", "", "", ""))
            for sample_name in sorted(fp.keys()):
                sample_grp = self._tree.insert(grp, tk.END, text=f"取样 {sample_name}", open=False, values=("", "", "", ""))
                sample = fp[sample_name]
                if isinstance(sample, dict):
                    for fid, entry in sorted(sample.items()):
                        if isinstance(entry, dict) and "raw_text" in entry:
                            self._insert_field(sample_grp, f"{sample_name}.{fid}", entry)

        # Group 3: Materials consumed
        mats = model.get("materials_consumed", [])
        if mats:
            grp = self._tree.insert("", tk.END, text="当日材料", open=False, values=("", "", "", ""))
            for i, row in enumerate(mats):
                if isinstance(row, dict):
                    for col_name, entry in sorted(row.items()):
                        if isinstance(entry, dict) and "raw_text" in entry:
                            self._insert_field(grp, f"材料[{i}].{col_name}", entry)

        # Group 4: Solids control
        solids = model.get("solids_control", [])
        if solids:
            grp = self._tree.insert("", tk.END, text="固控设备", open=False, values=("", "", "", ""))
            for i, row in enumerate(solids):
                if isinstance(row, dict):
                    for col_name, entry in sorted(row.items()):
                        if isinstance(entry, dict) and "raw_text" in entry:
                            self._insert_field(grp, f"固控[{i}].{col_name}", entry)

        # Group 5: Narratives
        narrs = model.get("narratives", {})
        if narrs:
            grp = self._tree.insert("", tk.END, text="长文本", open=False, values=("", "", "", ""))
            for nid, entry in sorted(narrs.items()):
                if isinstance(entry, dict) and "raw_text" in entry:
                    self._insert_field(grp, nid, entry, is_narrative=True)

        # Group 6: Material tracking (page 2)
        mt = model.get("material_tracking", {})
        if mt:
            grp = self._tree.insert("", tk.END, text="材料追踪 (第2页)", open=False, values=("", "", "", ""))
            # Summary rows
            summary = mt.get("summary", {})
            if summary:
                sgrp = self._tree.insert(grp, tk.END, text="费用汇总", open=True, values=("", "", "", ""))
                for label, entry in sorted(summary.items()):
                    if isinstance(entry, dict) and "raw_text" in entry:
                        self._insert_field(sgrp, f"汇总.{label}", entry)
            # Material rows
            materials = mt.get("materials", [])
            if materials:
                mgrp = self._tree.insert(grp, tk.END, text="材料消耗明细", open=False, values=("", "", "", ""))
                for i, row in enumerate(materials):
                    if isinstance(row, dict):
                        mat_name = row.get("material", {}).get("raw_text", f"材料{i}")
                        rgrp = self._tree.insert(mgrp, tk.END, text=mat_name, open=False, values=("", "", "", ""))
                        for col_name, entry in sorted(row.items()):
                            if isinstance(entry, dict) and "raw_text" in entry and col_name != "source":
                                self._insert_field(rgrp, f"材料追踪[{i}].{col_name}", entry)

        # Group 7: Fluid volume report (page 3)
        fv = model.get("fluid_volume_report", {})
        if fv:
            grp = self._tree.insert("", tk.END, text="钻井液数量 (第3页)", open=False, values=("", "", "", ""))
            # Tanks
            tanks = fv.get("tanks", [])
            if tanks:
                tgrp = self._tree.insert(grp, tk.END, text="罐容量", open=True, values=("", "", "", ""))
                for i, tank in enumerate(tanks):
                    if isinstance(tank, dict):
                        tno = tank.get("tank_no", {}).get("raw_text", f"罐{i}")
                        igrp = self._tree.insert(tgrp, tk.END, text=f"罐 {tno}", open=False, values=("", "", "", ""))
                        for col_name, entry in sorted(tank.items()):
                            if isinstance(entry, dict) and "raw_text" in entry and col_name != "source":
                                self._insert_field(igrp, f"罐[{i}].{col_name}", entry)
            # Wellbore
            wellbore = fv.get("wellbore", {})
            if wellbore:
                wgrp = self._tree.insert(grp, tk.END, text="井筒内泥浆", open=True, values=("", "", "", ""))
                for fid, entry in sorted(wellbore.items()):
                    if isinstance(entry, dict) and "raw_text" in entry:
                        self._insert_field(wgrp, f"井筒.{fid}", entry)
            # Balance
            balance = fv.get("balance", {})
            if balance:
                bgrp = self._tree.insert(grp, tk.END, text="钻井液平衡", open=True, values=("", "", "", ""))
                for fid, entry in sorted(balance.items()):
                    if isinstance(entry, dict) and "raw_text" in entry:
                        self._insert_field(bgrp, f"平衡.{fid}", entry)

    def get_edited_model(self) -> dict:
        """Return the business model with user edits applied."""
        if not self._edited:
            return self._model
        # Shallow copy is enough — we only replace top-level values
        import copy
        model = copy.deepcopy(self._model)
        for key, new_value in self._edited.items():
            entry = self._resolve_key(model, key)
            if entry is not None:
                entry["raw_text"] = new_value
                entry["value"] = new_value
                entry.setdefault("user_edited", True)
        return model

    # ── Internal ───────────────────────────────────────────

    def _insert_field(self, parent: str, fid: str, entry: dict, is_narrative: bool = False):
        """Insert one field row into the Treeview."""
        raw = entry.get("raw_text", "")
        conf = entry.get("confidence", 0)
        warnings = entry.get("warnings", [])
        source = entry.get("source", {})
        page = source.get("page", "")

        # Display value — truncate long narratives
        display_val = raw.replace("\n", " ")
        if len(display_val) > 80:
            display_val = display_val[:77] + "..."

        # Confidence display
        conf_str = f"{conf:.2f}" if conf else ""

        # Status
        status = "⚠" if warnings else "✓"
        if fid in self._edited:
            status = "✎已改"

        # Pick color tag
        tag = ""
        if warnings:
            tag = WARN_TAG
        else:
            for threshold, tag_name, _ in CONF_TAGS:
                if conf >= threshold:
                    tag = tag_name
                    break

        self._tree.insert(
            parent, tk.END,
            iid=fid, text=fid,
            values=(display_val, conf_str, page, status),
            tags=(tag,) if tag else (),
        )

    def _on_select(self, _event):
        """Highlight the source region on PDF when a field is selected."""
        sel = self._tree.selection()
        if not sel:
            return
        iid = sel[0]
        entry = self._find_entry(iid)
        if entry is None:
            return
        source = entry.get("source", {})
        bbox = source.get("bbox")
        page = source.get("page")
        if bbox and page and self._on_highlight:
            self._on_highlight(bbox, page)

    def _on_double_click(self, _event):
        """Start editing the selected field value."""
        sel = self._tree.selection()
        if not sel:
            return
        iid = sel[0]
        entry = self._find_entry(iid)
        if entry is None:
            return

        self._editing_iid = iid
        current_val = entry.get("raw_text", "")
        self._edit_var.set(current_val)
        self._edit_frame.pack(fill=tk.X, padx=4, pady=4, before=self._tree.master)
        self._edit_entry.focus_set()
        self._edit_entry.select_range(0, tk.END)

    def _confirm_edit(self):
        """Apply the edited value."""
        if not self._editing_iid:
            return
        new_val = self._edit_var.get()
        self._edited[self._editing_iid] = new_val

        # Update Treeview display
        vals = list(self._tree.item(self._editing_iid, "values"))
        display = new_val.replace("\n", " ")
        if len(display) > 80:
            display = display[:77] + "..."
        vals[0] = display
        vals[3] = "✎已改"
        self._tree.item(self._editing_iid, values=vals)

        self._cancel_edit()

    def _cancel_edit(self):
        """Hide the edit frame."""
        self._editing_iid = None
        self._edit_frame.pack_forget()

    def _find_entry(self, fid: str) -> dict | None:
        """Look up a field entry from the model by its tree iid."""
        model = self._model
        return self._resolve_key(model, fid)

    @staticmethod
    def _resolve_key(model: dict, key: str) -> dict | None:
        """Resolve a dotted field key like '#1.density_gcm3' or '材料[0].code'
        back to the dict entry in the business model.
        """
        # Try direct meta lookup first
        meta = model.get("meta", {})
        if key in meta:
            return meta[key]

        # Fluid properties: "sample.field_id"
        fp = model.get("fluid_properties", {})
        if "." in key:
            sample, fid = key.split(".", 1)
            if sample in fp and isinstance(fp[sample], dict) and fid in fp[sample]:
                return fp[sample][fid]

        # Materials: "材料[i].col"
        if key.startswith("材料["):
            try:
                idx_str = key.split("[")[1].split("]")[0]
                col = key.split("].")[1]
                idx = int(idx_str)
                mats = model.get("materials_consumed", [])
                if idx < len(mats) and col in mats[idx]:
                    return mats[idx][col]
            except (IndexError, ValueError):
                pass

        # Solids: "固控[i].col"
        if key.startswith("固控["):
            try:
                idx_str = key.split("[")[1].split("]")[0]
                col = key.split("].")[1]
                idx = int(idx_str)
                solids = model.get("solids_control", [])
                if idx < len(solids) and col in solids[idx]:
                    return solids[idx][col]
            except (IndexError, ValueError):
                pass

        # Material tracking: "材料追踪[i].col"
        if key.startswith("材料追踪["):
            try:
                idx_str = key.split("[")[1].split("]")[0]
                col = key.split("].")[1]
                idx = int(idx_str)
                mt = model.get("material_tracking", {})
                mats = mt.get("materials", [])
                if idx < len(mats) and col in mats[idx]:
                    return mats[idx][col]
            except (IndexError, ValueError):
                pass

        # Tanks: "罐[i].col"
        if key.startswith("罐["):
            try:
                idx_str = key.split("[")[1].split("]")[0]
                col = key.split("].")[1]
                idx = int(idx_str)
                fv = model.get("fluid_volume_report", {})
                tanks = fv.get("tanks", [])
                if idx < len(tanks) and col in tanks[idx]:
                    return tanks[idx][col]
            except (IndexError, ValueError):
                pass

        # Wellbore: "井筒.field"
        if key.startswith("井筒."):
            fid = key.split(".", 1)[1]
            fv = model.get("fluid_volume_report", {})
            wb = fv.get("wellbore", {})
            if fid in wb:
                return wb[fid]

        # Balance: "平衡.field"
        if key.startswith("平衡."):
            fid = key.split(".", 1)[1]
            fv = model.get("fluid_volume_report", {})
            bal = fv.get("balance", {})
            if fid in bal:
                return bal[fid]

        # Summary: "汇总.label"
        if key.startswith("汇总."):
            label = key.split(".", 1)[1]
            mt = model.get("material_tracking", {})
            summary = mt.get("summary", {})
            if label in summary:
                return summary[label]

        # Narratives: direct key
        narrs = model.get("narratives", {})
        if key in narrs:
            return narrs[key]

        return None
