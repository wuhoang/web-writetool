"""Browser UIA diagnostics: inspect what controls Chrome exposes."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any


class BrowserDiag(tk.Toplevel):
    """Show UIA tree of the connected browser window."""

    def __init__(self, master: tk.Widget, browser_window: Any):
        super().__init__(master)
        self.title("浏览器控件诊断")
        self.geometry("900x600")
        self._browser = browser_window

        # Top info
        info = ttk.Frame(self)
        info.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(info, text=f"窗口: {browser_window.window_text()}").pack(anchor=tk.W)

        btn_bar = ttk.Frame(self)
        btn_bar.pack(fill=tk.X, padx=8, pady=2)
        ttk.Button(btn_bar, text="扫描 Edit 控件", command=self._scan_edits).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_bar, text="扫描 ComboBox", command=self._scan_combos).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_bar, text="扫描所有控件", command=self._scan_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_bar, text="搜索 ID", command=self._search_id).pack(side=tk.LEFT, padx=2)
        self._search_var = tk.StringVar()
        ttk.Entry(btn_bar, textvariable=self._search_var, width=20).pack(side=tk.LEFT, padx=2)

        # Result tree
        cols = ("type", "auto_id", "name", "rect", "visible")
        self._tree = ttk.Treeview(self, columns=cols, show="headings")
        self._tree.heading("type", text="控件类型")
        self._tree.heading("auto_id", text="AutomationId")
        self._tree.heading("name", text="Name")
        self._tree.heading("rect", text="矩形")
        self._tree.heading("visible", text="可见")
        self._tree.column("type", width=80)
        self._tree.column("auto_id", width=200)
        self._tree.column("name", width=200)
        self._tree.column("rect", width=200)
        self._tree.column("visible", width=60)

        scroll = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0), pady=4)
        scroll.pack(side=tk.RIGHT, fill=tk.Y, pady=4, padx=(0, 8))

        # Count label
        self._count_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self._count_var).pack(fill=tk.X, padx=8, pady=(0, 4))

    def _clear(self):
        self._tree.delete(*self._tree.get_children())

    def _add_ctrl(self, ctrl):
        try:
            ctype = ctrl.element_info.control_type or "?"
            aid = ctrl.element_info.automation_id or ""
            name = (ctrl.element_info.name or "")[:80]
            try:
                r = ctrl.rectangle()
                rect = f"({r.left},{r.top})-({r.right},{r.bottom})"
                visible = "✓" if r.left is not None else "✗"
            except Exception:
                rect = "(N/A)"
                visible = "?"
            self._tree.insert("", tk.END, values=(ctype, aid, name, rect, visible))
        except Exception:
            pass

    def _scan_edits(self):
        self._clear()
        edits = self._browser.descendants(control_type="Edit")
        for c in edits:
            self._add_ctrl(c)
        self._count_var.set(f"共 {len(edits)} 个 Edit 控件")

    def _scan_combos(self):
        self._clear()
        combos = self._browser.descendants(control_type="ComboBox")
        for c in combos:
            self._add_ctrl(c)
        self._count_var.set(f"共 {len(combos)} 个 ComboBox 控件")

    def _scan_all(self):
        self._clear()
        count = 0
        for c in self._browser.descendants():
            try:
                aid = c.element_info.automation_id or ""
                name = c.element_info.name or ""
                if aid or name:
                    self._add_ctrl(c)
                    count += 1
            except Exception:
                pass
        self._count_var.set(f"共 {count} 个有标识的控件")

    def _search_id(self):
        keyword = self._search_var.get().strip()
        if not keyword:
            return
        self._clear()
        count = 0
        for c in self._browser.descendants():
            try:
                aid = c.element_info.automation_id or ""
                name = c.element_info.name or ""
                if keyword.lower() in aid.lower() or keyword.lower() in name.lower():
                    self._add_ctrl(c)
                    count += 1
            except Exception:
                pass
        self._count_var.set(f"搜索 '{keyword}': 找到 {count} 个匹配控件")
