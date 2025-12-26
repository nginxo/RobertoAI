import subprocess
import sys
import os
import threading
import tkinter as tk
from tkinter import ttk

BASE_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))

ROBERTO_PATH = os.path.join(BASE_DIR, "RobertoAI.exe")
WAKEONCALL_PATH = os.path.join(BASE_DIR, "services", "WakeOnCallService", "WakeOnCallService.exe")

def start_processes():
    try:
        subprocess.Popen([ROBERTO_PATH], shell=False)
        subprocess.Popen([WAKEONCALL_PATH], cwd=os.path.dirname(WAKEONCALL_PATH))
    except Exception as e:
        print("Errore nell'avvio dei processi:", e)

def main():
    root = tk.Tk()
    root.title("Launcher RobertoAI")
    root.geometry("420x150")
    root.resizable(False, False)

    root.update_idletasks()
    x = (root.winfo_screenwidth() // 2) - (root.winfo_width() // 2)
    y = (root.winfo_screenheight() // 2) - (root.winfo_height() // 2)
    root.geometry(f"+{x}+{y}")

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    frame = ttk.Frame(root, padding=20)
    frame.pack(fill="both", expand=True)

    label_title = ttk.Label(frame, text="Avvio servizi di RobertoAI...", font=("Segoe UI", 12, "bold"))
    label_title.pack(pady=(0, 10))

    label_info = ttk.Label(
        frame,
        text="Attendere qualche secondo mentre i servizi si avviano.",
        font=("Segoe UI", 9)
    )
    label_info.pack(pady=(0, 10))

    progress = ttk.Progressbar(frame, mode="indeterminate", length=300)
    progress.pack(pady=(0, 10))
    progress.start(10)

    def background_start():
        start_processes()
        root.after(3000, lambda: (progress.stop(), root.destroy()))

    threading.Thread(target=background_start, daemon=True).start()

    root.mainloop()

if __name__ == "__main__":
    main()
