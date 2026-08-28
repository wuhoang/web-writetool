"""PDF viewer widget: PyMuPDF rendering → tkinter Canvas.

Renders pages as PPM (no PIL dependency), supports page navigation,
zoom, and source-region highlighting.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

import pymupdf


class PdfViewer(ttk.Frame):
    """Left panel: PDF page display with navigation and highlight."""

    def __init__(self, master: tk.Widget):
        super().__init__(master)
        self._doc: pymupdf.Document | None = None
        self._page_num: int = 0
        self._zoom: float = 1.5
        self._photo: tk.PhotoImage | None = None  # prevent GC
        self._highlight_ids: list[int] = []
        self._build_ui()

    def _build_ui(self):
        # Canvas
        self._canvas = tk.Canvas(self, bg="#e0e0e0", highlightthickness=0)
        self._canvas.pack(fill=tk.BOTH, expand=True)

        # Bottom bar: prev / page label / next / zoom slider
        bar = ttk.Frame(self)
        bar.pack(fill=tk.X, side=tk.BOTTOM)

        self._btn_prev = ttk.Button(bar, text="◀ 上一页", width=10, command=self._prev_page)
        self._btn_prev.pack(side=tk.LEFT, padx=4, pady=4)

        self._page_label = ttk.Label(bar, text="— / —")
        self._page_label.pack(side=tk.LEFT, padx=8)

        self._btn_next = ttk.Button(bar, text="下一页 ▶", width=10, command=self._next_page)
        self._btn_next.pack(side=tk.LEFT, padx=4)

        ttk.Label(bar, text="缩放:").pack(side=tk.LEFT, padx=(20, 4))
        self._zoom_var = tk.DoubleVar(value=self._zoom)
        zoom_slider = ttk.Scale(
            bar, from_=0.5, to=3.0, variable=self._zoom_var,
            orient=tk.HORIZONTAL, length=120, command=self._on_zoom_change,
        )
        zoom_slider.pack(side=tk.LEFT, padx=4)

    # ── Public API ─────────────────────────────────────────

    def load_pdf(self, path: str | Path):
        """Open a PDF file and render page 1."""
        self._doc = pymupdf.open(str(path))
        self._page_num = 0
        self._render_current()

    def goto_page(self, page_num: int):
        """Jump to a 1-based page number."""
        if self._doc is None:
            return
        page_num = max(1, min(page_num, len(self._doc)))
        self._page_num = page_num - 1
        self._render_current()

    def highlight_region(self, bbox: list[float], page_num: int):
        """Draw a red rectangle on the given page at bbox=[x0,y0,x1,y1].

        If page_num differs from current page, switches first.
        Coordinates are in PDF points (72 dpi), scaled by current zoom.
        """
        if self._doc is None:
            return
        if page_num != self._page_num + 1:
            self.goto_page(page_num)

        # Clear old highlights
        for hid in self._highlight_ids:
            self._canvas.delete(hid)
        self._highlight_ids.clear()

        z = self._zoom
        x0, y0, x1, y1 = bbox
        # PDF coords → canvas coords (with offset for centering)
        page = self._doc[self._page_num]
        pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False)
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        ox = max(0, (cw - pix.width) // 2)
        oy = max(0, (ch - pix.height) // 2)

        sx0, sy0 = ox + x0 * z, oy + y0 * z
        sx1, sy1 = ox + x1 * z, oy + y1 * z

        rect_id = self._canvas.create_rectangle(
            sx0, sy0, sx1, sy1,
            outline="red", width=2, dash=(4, 2),
        )
        self._highlight_ids.append(rect_id)

        # Auto-scroll canvas to show the highlight
        self._canvas.xview_moveto(max(0, (sx0 - 50) / max(pix.width, 1)))
        self._canvas.yview_moveto(max(0, (sy0 - 50) / max(pix.height, 1)))

    def clear_highlights(self):
        """Remove all highlight rectangles."""
        for hid in self._highlight_ids:
            self._canvas.delete(hid)
        self._highlight_ids.clear()

    @property
    def page_count(self) -> int:
        return len(self._doc) if self._doc else 0

    @property
    def current_page(self) -> int:
        return self._page_num + 1

    # ── Internal ───────────────────────────────────────────

    def _render_current(self):
        if self._doc is None:
            return
        page = self._doc[self._page_num]
        z = self._zoom
        pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False)
        ppm = pix.tobytes("ppm")
        self._photo = tk.PhotoImage(data=ppm)

        self._canvas.delete("all")
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        ox = max(0, (cw - self._photo.width()) // 2)
        oy = max(0, (ch - self._photo.height()) // 2)
        self._canvas.create_image(ox, oy, anchor=tk.NW, image=self._photo)

        total = len(self._doc)
        self._page_label.config(text=f"{self._page_num + 1} / {total}")
        self._btn_prev.config(state=tk.NORMAL if self._page_num > 0 else tk.DISABLED)
        self._btn_next.config(state=tk.NORMAL if self._page_num < total - 1 else tk.DISABLED)

    def _prev_page(self):
        if self._page_num > 0:
            self._page_num -= 1
            self.clear_highlights()
            self._render_current()

    def _next_page(self):
        if self._doc and self._page_num < len(self._doc) - 1:
            self._page_num += 1
            self.clear_highlights()
            self._render_current()

    def _on_zoom_change(self, _value: str):
        try:
            self._zoom = float(_value)
        except ValueError:
            return
        if self._doc:
            self._render_current()
