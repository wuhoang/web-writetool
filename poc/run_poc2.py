"""
run_poc2.py — POC-2 端到端编排

UIA 定位 + pyautogui 写入。Chrome 启用 --force-renderer-accessibility。

用法:
  python poc/run_poc2.py                     # 默认 test_page
  python poc/run_poc2.py test_no_id          # 无ID页面 (by_name策略)
  python poc/run_poc2.py test_vertical       # 垂直布局
  python poc/run_poc2.py test_enterprise     # 仿真企业系统
  python poc/run_poc2.py test_dense_table    # 密集表格
  python poc/run_poc2.py all                 # 依次运行所有页面
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)
    sys.stderr = open(sys.stderr.fileno(), mode="w", encoding="utf-8", buffering=1)

ROOT = Path(__file__).resolve().parent.parent
POC_DIR = ROOT / "poc"
CONFIG_DIR = ROOT / "config"
OUTPUT_DIR = POC_DIR / "output"
BUSINESS_MODEL_PATH = OUTPUT_DIR / "business_model.json"
UI_MAPPING_PATH = CONFIG_DIR / "ui_mapping.yaml"

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

# 所有可用的测试页面
ALL_PAGES = ["test_page", "test_no_id", "test_vertical", "test_enterprise", "test_dense_table"]


def check_dependencies() -> bool:
    ok = True
    try:
        import pywinauto
        print(f"[依赖] pywinauto {pywinauto.__version__}")
    except ImportError:
        print("[错误] pywinauto 未安装"); ok = False
    try:
        import pyautogui
        print(f"[依赖] pyautogui {pyautogui.__version__}")
    except ImportError:
        print("[错误] pyautogui 未安装"); ok = False
    return ok


def load_configs():
    from ui_automation import load_business_model, load_ui_mapping
    if not BUSINESS_MODEL_PATH.exists():
        print(f"[错误] 业务模型不存在: {BUSINESS_MODEL_PATH}")
        print("  请先运行 python poc/run_poc1.py")
        sys.exit(1)
    return (
        load_business_model(str(BUSINESS_MODEL_PATH)),
        load_ui_mapping(str(UI_MAPPING_PATH)),
    )


def launch_chrome_with_accessibility(html_path: Path) -> bool:
    """用 --force-renderer-accessibility 启动 Chrome 打开页面"""
    if not os.path.exists(CHROME_PATH):
        print(f"[错误] Chrome 未找到: {CHROME_PATH}")
        return False
    url = str(html_path)
    print(f"[启动] Chrome --force-renderer-accessibility")
    subprocess.Popen([CHROME_PATH, "--force-renderer-accessibility", url])
    time.sleep(5)
    return True


def connect_to_browser(page_name: str = ""):
    """用 ctypes 快速查找并连接到 Chrome 窗口"""
    import ctypes
    from pywinauto import Application

    # 搜索关键词覆盖所有测试页面标题
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
        print("[错误] 未找到包含模拟页面的浏览器窗口")
        return None

    hwnd, title = found[0]
    print(f"[窗口] {title}")

    try:
        app = Application(backend="uia").connect(handle=hwnd)
        win = app.window(handle=hwnd)
        return win
    except Exception as e:
        print(f"[窗口] 连接失败: {e}")
        return None


def run_automation(browser_window, model: dict, mapping: dict, page_name: str = "test_page"):
    from ui_automation import run_fill
    print(f"\n{'=' * 60}")
    print(f"开始自动填写 ({page_name})")
    print(f"{'=' * 60}\n")
    return run_fill(browser_window, mapping, model, page_name=page_name)


def save_report(report_text: str, report_path: Path):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"\n[报告] 已保存: {report_path}")


def run_single_page(page_name: str, model: dict, mapping: dict) -> tuple:
    """运行单个测试页面，返回 (report, passed)"""
    page_cfg = mapping.get(page_name)
    if not page_cfg:
        print(f"[跳过] ui_mapping.yaml 中无 {page_name} 配置")
        return None, False

    html_file = POC_DIR / page_cfg["url"].replace("poc/", "")
    if not html_file.exists():
        print(f"[跳过] HTML 文件不存在: {html_file}")
        return None, False

    if not launch_chrome_with_accessibility(html_file):
        return None, False

    browser_win = connect_to_browser(page_name)
    if not browser_win:
        return None, False

    report = run_automation(browser_win, model, mapping, page_name=page_name)

    report_path = OUTPUT_DIR / f"poc2_{page_name}.txt"
    report_text = (
        f"POC-2 验证报告 — {page_name}\n"
        f"{'=' * 60}\n\n"
        f"测试页面: {html_file.name}\n"
        f"业务模型: {BUSINESS_MODEL_PATH.name}\n\n"
        f"{report.summary()}\n\n"
        f"{'=' * 60}\n"
        f"总结: {report.success_count}/{report.total} 字段填写成功\n"
    )
    print(f"\n{report_text}")
    save_report(report_text, report_path)

    has_input = any(r.success for r in report.results
                    if r.field_name in ("well_name", "oilfield", "rig"))
    has_select = any(r.success for r in report.results
                     if r.field_name in ("well_type", "fluid_type", "current_operation"))
    has_textarea = any(r.success for r in report.results
                       if r.field_name in ("engineering_summary", "treatment_log"))

    print(f"\n{'─' * 60}")
    print(f"POC-2 验证标准 ({page_name}):")
    print(f"  [{'OK' if has_input else 'FAIL'}] 文本输入框填写")
    print(f"  [{'OK' if has_select else 'FAIL'}] 下拉框选择")
    print(f"  [{'OK' if has_textarea else 'FAIL'}] 多行文本框填写")
    passed = has_input and has_select and has_textarea
    if passed:
        print(f"\n*** {page_name} 验证通过! ***")
    else:
        print(f"\n{page_name} 部分验证未通过。")
    return report, passed


def main():
    # 解析命令行参数
    page_arg = sys.argv[1] if len(sys.argv) > 1 else "test_page"

    if page_arg == "all":
        pages = ALL_PAGES
    elif page_arg in ALL_PAGES:
        pages = [page_arg]
    else:
        print(f"未知页面: {page_arg}")
        print(f"可用: {', '.join(ALL_PAGES)}, all")
        sys.exit(1)

    print("POC-2: UIA 定位 + pyautogui 写入 验证")
    print(f"测试页面: {', '.join(pages)}")
    print("=" * 60)

    if not check_dependencies():
        sys.exit(1)

    model, mapping = load_configs()
    print(f"[数据] 业务模型: meta {len(model.get('meta', {}))} 字段")

    results = {}
    for page_name in pages:
        print(f"\n{'#' * 60}")
        print(f"# 页面: {page_name}")
        print(f"{'#' * 60}")
        _, passed = run_single_page(page_name, model, mapping)
        results[page_name] = passed
        if page_name != pages[-1]:
            print("\n[等待] 3 秒后继续下一个页面...")
            time.sleep(3)

    # 汇总
    if len(pages) > 1:
        print(f"\n{'=' * 60}")
        print("全部测试汇总:")
        for name, ok in results.items():
            print(f"  [{'OK' if ok else 'FAIL'}] {name}")
        total_pass = sum(1 for v in results.values() if v)
        print(f"\n总计: {total_pass}/{len(results)} 页面通过")


if __name__ == "__main__":
    main()
