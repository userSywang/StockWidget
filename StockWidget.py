# filename: StockWidget.py
# python3 -m PyInstaller -F -w .\StockWidget.py --name StockWidget --icon .\StockWidget.ico --add-data ".\StockWidget.ico;."
import sys, ctypes
from App import App, APP_NAME

if __name__ == "__main__":
    mutex = None
    try:
        mutex = ctypes.windll.kernel32.CreateMutexW(None, False, f"{APP_NAME}.SingleInstance")
        if ctypes.windll.kernel32.GetLastError() == 183:
            sys.exit(0)
    except Exception:
        mutex = None
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"{APP_NAME}.1")
    except Exception:
        pass

    app = App(sys.argv)
    sys.exit(app.exec())
