"""
ui_automation.py — UIA 定位 + pyautogui 写入 (v8)

Locator: pywinauto UIA 找控件、获取屏幕坐标
Actor:   pyautogui 坐标点击 + 剪贴板粘贴
"""
from __future__ import annotations

import ctypes
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ── DPI 感知：必须在 pyautogui/pywinauto 初始化之前设置 ──
# 高 DPI 屏幕上如果不设置，UIA 返回逻辑坐标而 pyautogui 使用物理坐标，点击会偏移
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)  # Per-Monitor DPI Aware
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()  # System DPI Aware (fallback)
    except Exception:
        pass

import pyautogui
import pyperclip
import yaml

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.03


# ── 数据结构 ──────────────────────────────────────────────

class ControlType(str, Enum):
    INPUT = "input"
    SELECT = "select"
    TEXTAREA = "textarea"
    TABLE_CELL = "table_cell"


@dataclass
class LocateResult:
    found: bool
    control: Any = None
    center: tuple[int, int] = (0, 0)
    method: str = ""
    error: str = ""


@dataclass
class FillResult:
    field_name: str
    expected: str
    actual: str = ""
    success: bool = False
    method: str = ""
    error: str = ""
    elapsed_ms: float = 0


@dataclass
class FillReport:
    results: list[FillResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def fail_count(self) -> int:
        return self.total - self.success_count

    def summary(self) -> str:
        lines = [
            f"填写报告: {self.success_count}/{self.total} 成功",
            f"{'─' * 60}",
        ]
        for r in self.results:
            status = "OK" if r.success else "FAIL"
            lines.append(
                f"  [{status}] {r.field_name:<28s} "
                f"expected={r.expected!r:20s} "
                f"actual={r.actual!r:20s} "
                f"({r.method}, {r.elapsed_ms:.0f}ms)"
            )
            if r.error:
                lines.append(f"         -> {r.error}")
        return "\n".join(lines)


# ── 配置加载 ──────────────────────────────────────────────

def load_ui_mapping(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_business_model(path: str) -> dict:
    import json
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def resolve_model_path(model: dict, path: str) -> str:
    parts = path.split(".")
    obj = model
    for p in parts:
        if isinstance(obj, dict):
            obj = obj.get(p, {})
        elif isinstance(obj, list) and p.startswith("#"):
            idx = int(p[1:]) - 1
            obj = obj[idx] if 0 <= idx < len(obj) else {}
        else:
            return ""
    return str(obj) if obj else ""


# ── Locator (UIA) ────────────────────────────────────────

def _get_center(ctrl) -> tuple[int, int]:
    rect = ctrl.rectangle()
    cx = (rect.left + rect.right) // 2
    cy = (rect.top + rect.bottom) // 2
    return (cx, cy)


def locate_control(browser_window, spec: dict) -> LocateResult:
    strategy = spec.get("strategy", "")
    target = spec.get("target", "")
    try:
        if strategy == "by_id":
            ctrl = browser_window.child_window(auto_id=target)
        elif strategy == "by_name":
            ctrl = browser_window.child_window(title=target)
        elif strategy == "by_label":
            # 相邻标签推断：找到标签文本，取其右侧最近的 Edit 控件
            return _locate_by_label(browser_window, target)
        else:
            return LocateResult(found=False, error=f"unknown strategy: {strategy}")

        if not ctrl.exists(timeout=2):
            return LocateResult(found=False, error=f"{strategy}={target!r} not found")

        cx, cy = _get_center(ctrl)
        return LocateResult(found=True, control=ctrl, center=(cx, cy), method=strategy)
    except Exception as e:
        return LocateResult(found=False, error=str(e))


def _locate_by_label(browser_window, label_text: str) -> LocateResult:
    """相邻标签推断：找到标签 StaticText，取其右侧或下方最近的 Edit/ComboBox"""
    try:
        # 搜索包含标签文本的元素（Text / Header 等）
        label_types = ["Text", "Header", "DataItem"]
        target_label = None
        for ctype in label_types:
            for label in browser_window.descendants(control_type=ctype):
                try:
                    name = label.element_info.name or ""
                    if label_text in name:
                        target_label = label
                        break
                except Exception:
                    continue
            if target_label:
                break

        if not target_label:
            return LocateResult(found=False, error=f"label {label_text!r} not found")

        label_rect = target_label.rectangle()
        label_cx = (label_rect.left + label_rect.right) // 2
        label_cy = (label_rect.top + label_rect.bottom) // 2

        # 搜索所有 Edit 和 ComboBox 控件
        edits = browser_window.descendants(control_type="Edit")
        combos = browser_window.descendants(control_type="ComboBox")
        candidates = edits + combos

        best = None
        best_dist = 99999
        for c in candidates:
            try:
                cr = c.rectangle()
                ccx = (cr.left + cr.right) // 2
                ccy = (cr.top + cr.bottom) // 2
                # 标签右侧（同行）或正下方（表头列）
                same_row = abs(ccy - label_cy) < 30
                below = ccy > label_rect.bottom and ccy < label_rect.bottom + 60
                right_of = ccx > label_rect.left
                if (same_row or below) and right_of:
                    dist = abs(ccx - label_cx) + abs(ccy - label_cy) * 2
                    if dist < best_dist:
                        best_dist = dist
                        best = c
            except Exception:
                continue

        if best:
            cx, cy = _get_center(best)
            return LocateResult(found=True, control=best, center=(cx, cy), method="by_label")
        return LocateResult(found=False, error=f"no input near label {label_text!r}")
    except Exception as e:
        return LocateResult(found=False, error=str(e))


# ── 通用工具 ──────────────────────────────────────────────

def _force_foreground(browser_window):
    import ctypes
    try:
        ctypes.windll.user32.SetForegroundWindow(browser_window.handle)
    except Exception:
        browser_window.set_focus()
    time.sleep(0.05)


# ── Actor ─────────────────────────────────────────────────

def _fill_input(x: int, y: int, value: str, screen_h: int):
    """填写输入框/textarea：click → Ctrl+A → Delete → 粘贴"""
    safe_y = min(max(y, 10), screen_h - 50)
    pyautogui.click(x, safe_y)
    time.sleep(0.08)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.02)
    pyautogui.press("delete")
    time.sleep(0.02)
    pyperclip.copy(value)
    time.sleep(0.02)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.08)


def _select_dropdown(x: int, y: int, value: str, screen_h: int,
                     option_index: int = -1, options: list[str] | None = None):
    """选择下拉框：click → Home → Down N → Enter

    option_index 是 HTML <select> 的 option 序号（从 0 开始，包含空白项）。
    如果没传 index，从 options 列表按 value 查找。
    """
    safe_y = min(max(y, 10), screen_h - 50)
    pyautogui.click(x, safe_y)
    time.sleep(0.15)

    # 确定目标 index
    if option_index < 0 and options:
        if value in options:
            option_index = options.index(value)

    if option_index >= 0:
        pyautogui.press("home")
        time.sleep(0.05)
        for _ in range(option_index):
            pyautogui.press("down")
            time.sleep(0.03)
    pyautogui.press("enter")
    time.sleep(0.1)


def _read_back(x: int, y: int, screen_h: int) -> str:
    """回读控件值：click → Ctrl+A → Ctrl+C → 剪贴板"""
    safe_y = min(max(y, 10), screen_h - 50)
    pyautogui.click(x, safe_y)
    time.sleep(0.08)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.02)
    pyautogui.hotkey("ctrl", "c")
    time.sleep(0.06)
    return pyperclip.paste().strip()


# ── 滚动 ──────────────────────────────────────────────────

def _scroll_into_view(browser_window, ctrl, screen_h: int, max_scrolls: int = 30):
    """自适应步长滚动，目标 y=200~600"""
    _force_foreground(browser_window)
    time.sleep(0.15)

    for i in range(max_scrolls):
        cx, cy = _get_center(ctrl)
        if 200 < cy < 600:
            return
        dist = abs(cy - 400)
        step = -15 if dist > 300 else (-5 if dist > 100 else -2)
        if cy < 200:
            step = -step
        pyautogui.scroll(step)
        time.sleep(0.12)
        if i % 5 == 0:
            _force_foreground(browser_window)


# ── Runner ────────────────────────────────────────────────

def run_fill(
    browser_window,
    mapping_config: dict,
    business_model: dict,
    page_name: str = "test_page",
) -> FillReport:
    """执行完整填写流程"""
    page_cfg = mapping_config.get(page_name, {})
    fields = page_cfg.get("fields", {})
    report = FillReport()
    screen_h = pyautogui.size()[1]

    # 回到页面顶部
    _force_foreground(browser_window)
    pyautogui.press("home")
    time.sleep(0.3)
    fg_set = True

    for field_name, field_cfg in fields.items():
        locator_spec = field_cfg.get("locator", {})
        control_type = ControlType(field_cfg.get("control_type", "input"))
        model_path = field_cfg.get("model_path", "")
        element_id = locator_spec.get("target", "")

        value = resolve_model_path(business_model, model_path)
        if not value:
            report.results.append(FillResult(
                field_name=field_name, expected="(empty)",
                error="model_path resolved to empty", method="skip",
            ))
            continue

        t0 = time.time()
        loc = locate_control(browser_window, locator_spec)
        if not loc.found:
            report.results.append(FillResult(
                field_name=field_name, expected=value,
                error=loc.error, method="locate_failed",
            ))
            continue

        try:
            cx, cy = loc.center
            # 需要滚动时重新设置前台
            if cy > 600 or cy < 200:
                _scroll_into_view(browser_window, loc.control, screen_h)
                cx, cy = _get_center(loc.control)
                fg_set = True

            # 填写
            if control_type == ControlType.SELECT:
                option_index = field_cfg.get("option_index", -1)
                options = field_cfg.get("options", None)
                _select_dropdown(cx, cy, value, screen_h, option_index, options)
            else:
                _fill_input(cx, cy, value, screen_h)

            elapsed = (time.time() - t0) * 1000

            # 回读验证
            if not fg_set:
                _force_foreground(browser_window)
            if control_type == ControlType.SELECT:
                readback = None  # select 无法通过剪贴板回读
            else:
                readback = _read_back(cx, cy, screen_h)

            success = (readback is None) or (readback == value.strip())
            actual_display = readback if readback is not None else "(unverified)"
            report.results.append(FillResult(
                field_name=field_name, expected=value, actual=actual_display,
                success=success, method="pyautogui", elapsed_ms=elapsed,
            ))
            fg_set = False

        except Exception as e:
            elapsed = (time.time() - t0) * 1000
            report.results.append(FillResult(
                field_name=field_name, expected=value,
                error=str(e), method="pyautogui", elapsed_ms=elapsed,
            ))

    return report
