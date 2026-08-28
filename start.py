"""启动器 — 双击运行或 python start.py"""
import sys
import os

# 确保工作目录正确
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# 确保项目根目录在 sys.path
root = os.path.dirname(os.path.abspath(__file__))
if root not in sys.path:
    sys.path.insert(0, root)

try:
    from gui.app import MainApp
    app = MainApp()
    app.mainloop()
except Exception as e:
    import traceback
    detail = traceback.format_exc()
    # 优先弹窗，fallback 到控制台
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("启动失败", f"{e}\n\n{detail}")
        root.destroy()
    except Exception:
        print(detail)
        print(f"\n启动失败: {e}")
        input("按回车键退出...")
