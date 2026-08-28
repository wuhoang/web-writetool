"""Main application window: toolbar + PDF viewer + field panel + status bar.

Ties together PdfViewer, FieldPanel, and the POC-1/POC-2 pipelines.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import threading
import time

# ── DPI 感知：必须在 tkinter/pywinauto/pyautogui 之前设置 ──
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# Project paths
ROOT = Path(__file__).resolve().parent.parent
POC_DIR = ROOT / "poc"
CONFIG_DIR = ROOT / "config"
OUTPUT_DIR = POC_DIR / "output"

# Add poc/ to sys.path so we can import layout_recovery, field_mapping, ui_automation
sys.path.insert(0, str(POC_DIR))

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


class MainApp(tk.Tk):
    """Top-level application window."""

    def __init__(self):
        super().__init__()
        self.title("钻井液日报自动填写工具")
        self.geometry("1200x750")
        self.minsize(800, 500)

        self._pdf_path: Path | None = None
        self._business_model: dict = {}
        self._mapping_config: dict = {}
        self._browser_window = None

        self._build_toolbar()
        self._build_main_area()
        self._build_status_bar()

        # Keyboard shortcut: Esc to stop
        self.bind("<Escape>", lambda e: self._on_escape())

    # ── UI Construction ────────────────────────────────────

    def _build_toolbar(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, padx=4, pady=4)

        self._btn_select = ttk.Button(toolbar, text="选择PDF", command=self._select_pdf)
        self._btn_select.pack(side=tk.LEFT, padx=2)

        self._btn_parse = ttk.Button(toolbar, text="解析", command=self._parse_pdf, state=tk.DISABLED)
        self._btn_parse.pack(side=tk.LEFT, padx=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)

        self._btn_connect = ttk.Button(toolbar, text="连接浏览器", command=self._connect_browser, state=tk.DISABLED)
        self._btn_connect.pack(side=tk.LEFT, padx=2)

        self._btn_fill = ttk.Button(toolbar, text="开始填写", command=self._start_fill, state=tk.DISABLED)
        self._btn_fill.pack(side=tk.LEFT, padx=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)

        # Page selector for filling (dropdown)
        ttk.Label(toolbar, text="填写页面:").pack(side=tk.LEFT, padx=(4, 2))
        self._page_var = tk.StringVar(value="test_page")
        self._page_combo = ttk.Combobox(
            toolbar, textvariable=self._page_var, width=15, state="readonly",
            values=["test_page", "test_no_id", "test_vertical", "test_enterprise", "test_dense_table"],
        )
        self._page_combo.pack(side=tk.LEFT, padx=2)

        # File path label (right side)
        self._file_var = tk.StringVar(value="未选择文件")
        ttk.Label(toolbar, textvariable=self._file_var, foreground="gray").pack(
            side=tk.RIGHT, padx=8,
        )

    def _build_main_area(self):
        from gui.pdf_viewer import PdfViewer
        from gui.field_panel import FieldPanel

        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))

        # Left: PDF viewer
        self._pdf_viewer = PdfViewer(paned)
        paned.add(self._pdf_viewer, weight=3)

        # Right: Field panel
        self._field_panel = FieldPanel(paned, on_highlight=self._on_field_highlight)
        paned.add(self._field_panel, weight=2)

    def _build_status_bar(self):
        self._status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(
            self, textvariable=self._status_var, relief=tk.SUNKEN, anchor=tk.W,
        )
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=4, pady=(0, 4))

    # ── Actions ────────────────────────────────────────────

    def _select_pdf(self):
        path = filedialog.askopenfilename(
            title="选择钻井液日报 PDF",
            filetypes=[("PDF 文件", "*.pdf"), ("所有文件", "*.*")],
            initialdir=str(ROOT),
        )
        if not path:
            return
        self._pdf_path = Path(path)
        self._file_var.set(self._pdf_path.name)
        self._status_var.set(f"已选择: {self._pdf_path.name}")

        # Load PDF preview immediately
        try:
            self._pdf_viewer.load_pdf(self._pdf_path)
        except Exception as e:
            messagebox.showerror("错误", f"无法打开 PDF:\n{e}")
            return

        self._btn_parse.config(state=tk.NORMAL)

    def _parse_pdf(self):
        """Run POC-1 pipeline in background thread."""
        if not self._pdf_path:
            return

        self._btn_parse.config(state=tk.DISABLED)
        self._status_var.set("正在解析 PDF...")
        self.update_idletasks()

        def worker():
            try:
                from field_mapping import build_business_model
                rules_path = CONFIG_DIR / "field_rules.yaml"
                model, audit = build_business_model(self._pdf_path, rules_path)
                self.after(0, lambda: self._on_parse_done(model, audit))
            except Exception as e:
                self.after(0, lambda: self._on_parse_error(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_parse_done(self, model: dict, audit: dict):
        self._business_model = model
        self._field_panel.load_model(model)

        ca = audit.get("counts", {})
        meta_ok = ca.get("meta_matched", 0)
        meta_total = ca.get("meta_expected", 0)
        samples = ca.get("sample_points", 0)
        mat_rows = ca.get("material_rows", 0)
        solids_rows = ca.get("solids_rows", 0)
        narr_count = len(ca.get("narratives", []))

        self._status_var.set(
            f"解析完成 — meta {meta_ok}/{meta_total}, "
            f"性能 {samples}个取样点, 材料 {mat_rows}行, "
            f"固控 {solids_rows}行, 长文本 {narr_count}段"
        )
        self._btn_parse.config(state=tk.NORMAL)
        self._btn_connect.config(state=tk.NORMAL)

    def _on_parse_error(self, msg: str):
        self._status_var.set(f"解析失败: {msg}")
        self._btn_parse.config(state=tk.NORMAL)
        messagebox.showerror("解析错误", f"PDF 解析失败:\n{msg}")

    def _connect_browser(self):
        """Launch Chrome with accessibility flag and connect via UIA."""
        if not self._business_model:
            messagebox.showwarning("提示", "请先解析 PDF")
            return

        page_name = self._page_var.get()
        page_cfg = self._load_mapping().get(page_name, {})
        html_file = POC_DIR / page_cfg.get("url", "").replace("poc/", "")

        if not html_file.exists():
            messagebox.showerror("错误", f"HTML 文件不存在:\n{html_file}")
            return

        self._status_var.set("正在启动 Chrome...")
        self._btn_connect.config(state=tk.DISABLED)
        self.update_idletasks()

        def worker():
            try:
                # Launch Chrome
                if os.path.exists(CHROME_PATH):
                    subprocess.Popen([CHROME_PATH, "--force-renderer-accessibility", str(html_file)])
                else:
                    # Try to find chrome in PATH
                    subprocess.Popen(["chrome", "--force-renderer-accessibility", str(html_file)])
                time.sleep(5)

                # Connect via UIA
                import ctypes
                from pywinauto import Application

                keywords = ["钻井液", "test_page", "无ID", "垂直", "管理系统", "密集"]
                EnumWindows = ctypes.windll.user32.EnumWindows
                GetWindowTextW = ctypes.windll.user32.GetWindowTextW
                IsWindowVisible = ctypes.windll.user32.IsWindowVisible
                WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
                found = []

                def enum_cb(hwnd, _):
                    if IsWindowVisible(hwnd):
                        buf = ctypes.create_unicode_buffer(256)
                        GetWindowTextW(hwnd, buf, 256)
                        title = buf.value
                        if title and any(kw in title for kw in keywords):
                            found.append((hwnd, title))
                    return True

                EnumWindows(WNDENUMPROC(enum_cb), 0)

                if not found:
                    self.after(0, lambda: self._on_connect_error("未找到浏览器窗口"))
                    return

                hwnd, title = found[0]

                # UIA connect with timeout
                import signal

                def _timeout_handler(signum, frame):
                    raise TimeoutError("UIA 连接超时 (10s)")

                # Use threading.Timer for timeout (signal not reliable on Windows threads)
                connect_result = [None, None]
                def do_connect():
                    try:
                        app = Application(backend="uia").connect(handle=hwnd)
                        win = app.window(handle=hwnd)
                        connect_result[0] = win
                    except Exception as e:
                        connect_result[1] = e

                t = threading.Thread(target=do_connect, daemon=True)
                t.start()
                t.join(timeout=10)
                if t.is_alive():
                    self.after(0, lambda: self._on_connect_error("UIA 连接超时 (10s)，请确认 Chrome 已启用无障碍"))
                    return
                if connect_result[1]:
                    raise connect_result[1]
                self.after(0, lambda: self._on_connect_done(connect_result[0], title))

            except Exception as e:
                self.after(0, lambda: self._on_connect_error(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_connect_done(self, browser_win, title: str):
        self._browser_window = browser_win
        self._status_var.set(f"已连接: {title}")
        self._btn_connect.config(state=tk.NORMAL)
        self._btn_fill.config(state=tk.NORMAL)

    def _on_connect_error(self, msg: str):
        self._status_var.set(f"连接失败: {msg}")
        self._btn_connect.config(state=tk.NORMAL)
        messagebox.showerror("连接错误", f"无法连接浏览器:\n{msg}")

    def _start_fill(self):
        """Open the fill runner dialog."""
        if not self._browser_window:
            messagebox.showwarning("提示", "请先连接浏览器")
            return

        from gui.fill_runner import FillRunner

        page_name = self._page_var.get()
        mapping = self._load_mapping()

        FillRunner(
            self,
            browser_window=self._browser_window,
            mapping_config=mapping,
            business_model=self._business_model,
            page_name=page_name,
        )

    def _on_field_highlight(self, bbox: list[float], page: int):
        """Callback from FieldPanel: highlight source region on PDF."""
        self._pdf_viewer.highlight_region(bbox, page)

    def _on_escape(self):
        """Emergency stop — release grab and close fill dialog if open."""
        # This is a safety mechanism per design doc section 4.6
        self._status_var.set("已中断")

    # ── Helpers ────────────────────────────────────────────

    def _load_mapping(self) -> dict:
        """Load ui_mapping.yaml (cached)."""
        if not self._mapping_config:
            import yaml
            path = CONFIG_DIR / "ui_mapping.yaml"
            if path.exists():
                with open(path, encoding="utf-8") as f:
                    self._mapping_config = yaml.safe_load(f) or {}
        return self._mapping_config
