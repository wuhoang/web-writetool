"""Entry point for the MVP-GUI application.

Usage:
    python -m gui.run_app
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main():
    from gui.app import MainApp
    app = MainApp()
    app.mainloop()


if __name__ == "__main__":
    main()
