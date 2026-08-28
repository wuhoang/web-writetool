"""Fill runner dialog: progress bar + per-field status + result summary + cancel.

Runs ui_automation.run_fill() in a background thread to keep the GUI responsive.
Supports cancellation via a stop flag checked between fields.
"""
from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import ttk
from typing import Any


class FillRunner(tk.Toplevel):
    """Modal dialog that runs the web auto-fill and shows progress."""

    def __init__(
        self,
        master: tk.Widget,
        browser_window: Any,
        mapping_config: dict,
        business_model: dict,
        page_name: str = "test_page",
    ):
        super().__init__(master)
        self.title("自动填写")
        self.geometry("560x450")
        self.resizable(True, True)
        self.transient(master)
        self.grab_set()

        self._browser = browser_window
        self._mapping = mapping_config
        self._model = business_model
        self._page_name = page_name
        self._report = None
        self._cancelled = False
        self._fill_thread: threading.Thread | None = None

        self._build_ui()
        self.after(200, self._start_fill)

    def _build_ui(self):
        # Current field label
        self._status_var = tk.StringVar(value="准备中...")
        ttk.Label(self, textvariable=self._status_var, font=("", 10)).pack(
            fill=tk.X, padx=10, pady=(10, 4),
        )

        # Progress bar
        self._progress = ttk.Progressbar(self, mode="determinate", length=400)
        self._progress.pack(fill=tk.X, padx=10, pady=4)

        # Result list
        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        columns = ("status", "field", "expected", "actual")
        self._tree = ttk.Treeview(
            frame, columns=columns, show="headings", selectmode="none",
        )
        self._tree.heading("status", text="状态")
        self._tree.heading("field", text="字段")
        self._tree.heading("expected", text="期望值")
        self._tree.heading("actual", text="实际值")
        self._tree.column("status", width=50, anchor=tk.CENTER)
        self._tree.column("field", width=140)
        self._tree.column("expected", width=130)
        self._tree.column("actual", width=130)

        vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self._tree.tag_configure("ok", foreground="green")
        self._tree.tag_configure("fail", foreground="red")
        self._tree.tag_configure("skip", foreground="gray")
        self._tree.tag_configure("cancel", foreground="orange")

        # Summary label
        self._summary_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self._summary_var, font=("", 10, "bold")).pack(
            fill=tk.X, padx=10, pady=(4, 6),
        )

        # Button bar: Cancel / Close
        btn_bar = ttk.Frame(self)
        btn_bar.pack(pady=(0, 10))

        self._btn_cancel = ttk.Button(btn_bar, text="取消填写", command=self._cancel_fill)
        self._btn_cancel.pack(side=tk.LEFT, padx=4)

        self._btn_close = ttk.Button(btn_bar, text="关闭", command=self.destroy, state=tk.DISABLED)
        self._btn_close.pack(side=tk.LEFT, padx=4)

        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

    def _start_fill(self):
        """Run fill in a background thread with per-field cancellation."""
        self._fill_thread = threading.Thread(target=self._fill_worker, daemon=True)
        self._fill_thread.start()

    def _fill_worker(self):
        """Background worker: run fill with cancellation support."""
        try:
            from ui_automation import (
                ControlType, FillReport, FillResult, _fill_input, _force_foreground,
                _get_center, _read_back, _scroll_into_view, _select_dropdown,
                load_business_model, load_ui_mapping, locate_control, resolve_model_path,
            )
            import pyautogui
            import pyperclip

            mapping_config = self._mapping
            business_model = self._model
            page_name = self._page_name

            page_cfg = mapping_config.get(page_name, {})
            fields = page_cfg.get("fields", {})
            report = FillReport()
            screen_h = pyautogui.size()[1]

            # Force foreground and go to top
            _force_foreground(self._browser)
            pyautogui.press("home")
            time.sleep(0.3)

            total = len(fields)
            field_list = list(fields.items())

            for i, (field_name, field_cfg) in enumerate(field_list):
                if self._cancelled:
                    report.results.append(FillResult(
                        field_name=field_name, expected="", method="cancelled",
                    ))
                    self.after(0, lambda fn=field_name, idx=i: self._on_field_progress(
                        idx, total, fn, "cancel", "已取消"))
                    continue

                locator_spec = field_cfg.get("locator", {})
                control_type = ControlType(field_cfg.get("control_type", "input"))
                model_path = field_cfg.get("model_path", "")

                value = resolve_model_path(business_model, model_path)
                if not value:
                    report.results.append(FillResult(
                        field_name=field_name, expected="(empty)",
                        error="model_path resolved to empty", method="skip",
                    ))
                    self.after(0, lambda fn=field_name, idx=i: self._on_field_progress(
                        idx, total, fn, "skip", "空值跳过"))
                    continue

                t0 = time.time()
                self.after(0, lambda fn=field_name, idx=i: self._on_field_progress(
                    idx, total, fn, "working", "定位中..."))

                try:
                    # Locate with timeout protection
                    loc = locate_control(self._browser, locator_spec)
                    if not loc.found:
                        elapsed = (time.time() - t0) * 1000
                        report.results.append(FillResult(
                            field_name=field_name, expected=value,
                            error=loc.error, method="locate_failed", elapsed_ms=elapsed,
                        ))
                        self.after(0, lambda fn=field_name, err=loc.error: self._on_field_progress(
                            -1, 0, fn, "fail", f"定位失败: {err}"))
                        continue

                    cx, cy = loc.center
                    if cy > 600 or cy < 200:
                        _scroll_into_view(self._browser, loc.control, screen_h)
                        cx, cy = _get_center(loc.control)

                    # Fill
                    if control_type == ControlType.SELECT:
                        option_index = field_cfg.get("option_index", -1)
                        options = field_cfg.get("options", None)
                        _select_dropdown(cx, cy, value, screen_h, option_index, options)
                    else:
                        _fill_input(cx, cy, value, screen_h)

                    elapsed = (time.time() - t0) * 1000

                    # Read back
                    if control_type == ControlType.SELECT:
                        readback = None
                    else:
                        readback = _read_back(cx, cy, screen_h)

                    success = (readback is None) or (readback == value.strip())
                    actual_display = readback if readback is not None else "(unverified)"
                    report.results.append(FillResult(
                        field_name=field_name, expected=value, actual=actual_display,
                        success=success, method="pyautogui", elapsed_ms=elapsed,
                    ))
                    status = "ok" if success else "fail"
                    self.after(0, lambda fn=field_name, st=status, av=actual_display: self._on_field_progress(
                        -1, 0, fn, st, av))

                except Exception as e:
                    elapsed = (time.time() - t0) * 1000
                    report.results.append(FillResult(
                        field_name=field_name, expected=value,
                        error=str(e), method="pyautogui", elapsed_ms=elapsed,
                    ))
                    self.after(0, lambda fn=field_name, err=str(e): self._on_field_progress(
                        -1, 0, fn, "fail", err))

            self._report = report
            self.after(0, self._on_complete)

        except Exception as e:
            self.after(0, lambda: self._on_error(str(e)))

    def _on_field_progress(self, index: int, total: int, field_name: str, status: str, detail: str):
        """Update progress for a single field (called on main thread)."""
        if index >= 0:
            self._progress["maximum"] = total
            self._progress["value"] = index + 1
            self._status_var.set(f"[{index + 1}/{total}] {field_name}")
        else:
            self._status_var.set(field_name)

        tag_map = {"ok": "ok", "fail": "fail", "skip": "skip", "cancel": "cancel", "working": ""}
        icon_map = {"ok": "✅", "fail": "❌", "skip": "⏭", "cancel": "⏹", "working": "⏳"}
        tag = tag_map.get(status, "")
        icon = icon_map.get(status, "?")

        self._tree.insert("", tk.END, values=(icon, field_name, "", detail), tags=(tag,) if tag else ())
        self._tree.see(tk.END)
        self.update_idletasks()

    def _on_complete(self):
        """Called on the main thread when fill is done."""
        report = self._report
        if report is None:
            return

        ok = report.success_count
        fail = report.fail_count
        total = report.total
        cancelled = sum(1 for r in report.results if r.method == "cancelled")

        if cancelled:
            self._summary_var.set(f"已取消: {ok}/{total - cancelled} 成功, {fail} 失败, {cancelled} 未执行")
            self._status_var.set("填写已取消")
        else:
            self._summary_var.set(f"完成: {ok}/{total} 成功, {fail} 失败")
            self._status_var.set("填写完成")

        self._btn_cancel.config(state=tk.DISABLED)
        self._btn_close.config(state=tk.NORMAL)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _on_error(self, error_msg: str):
        """Called if the fill thread raises an exception."""
        self._status_var.set(f"错误: {error_msg}")
        self._summary_var.set("填写失败")
        self._btn_cancel.config(state=tk.DISABLED)
        self._btn_close.config(state=tk.NORMAL)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _cancel_fill(self):
        """Signal the fill thread to stop after the current field."""
        self._cancelled = True
        self._btn_cancel.config(state=tk.DISABLED)
        self._status_var.set("正在取消（等待当前字段完成）...")

    def _on_window_close(self):
        """Handle window close button."""
        if self._fill_thread and self._fill_thread.is_alive():
            self._cancel_fill()
        else:
            self.destroy()

    @property
    def report(self):
        return self._report
