"""Entry point of a standalone game app made by GamebaseST: shows the game's screenshot as a
splash screen, then starts the Hatari bundled in the `payload` folder with the game's disk(s).

This file is frozen with PyInstaller by standalone.py, once per game and per operating system."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

SPLASH_MAX = (640, 480)
HATARI_AFTER_MS = 1500   # Hatari starts while the splash is still showing
SPLASH_MS = 3000


def payload_dir():
    exe = Path(sys.executable).resolve()
    if sys.platform == "darwin":  # <App>.app/Contents/MacOS/<exe>
        return exe.parents[1] / "Resources" / "payload"
    return exe.parent / "payload"


def user_data_dir(ident):
    """Where game saves and the Hatari config live: the app itself stays read-only."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / ident
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / ident
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / ident


def start_hatari(payload, info):
    data = user_data_dir(info["id"])
    disks_dir = data / "disks"
    disks_dir.mkdir(parents=True, exist_ok=True)
    config = data / "hatari.cfg"
    shutil.copyfile(payload / "hatari.cfg", config)  # Hatari rewrites it

    args = [str(payload / info["hatari"]), "--configfile", str(config),
            "--tos", str(payload / "tos.img")]
    for i, disk in enumerate(info["disks"]):
        target = disks_dir / disk
        if not target.exists():  # keep earlier game saves
            shutil.copyfile(payload / "disks" / disk, target)
        args += ["--disk-a" if i == 0 else "--disk-b", str(target)]
    args += info["args"]
    subprocess.Popen(args, cwd=disks_dir)


def show_splash(root, payload, info):
    """Borderless window with the screenshot scaled to fit, the game name and 'Loading...'."""
    from PIL import Image, ImageTk
    image = Image.open(payload / info["splash"]).convert("RGB")
    scale = min(SPLASH_MAX[0] / image.width, SPLASH_MAX[1] / image.height)
    image = image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)
    photo = ImageTk.PhotoImage(image)

    root.overrideredirect(True)
    root.configure(background="black")
    picture = tk.Label(root, image=photo, borderwidth=0, background="black")
    picture.image = photo  # keep a reference
    picture.pack()
    tk.Label(root, text=info["name"], foreground="white", background="black",
             font=("Helvetica", 18, "bold")).pack(pady=(10, 0))
    tk.Label(root, text="Loading...", foreground="#bbbbbb", background="black",
             font=("Helvetica", 12)).pack(pady=(0, 10))
    root.update_idletasks()
    x = (root.winfo_screenwidth() - root.winfo_reqwidth()) // 2
    y = (root.winfo_screenheight() - root.winfo_reqheight()) // 2
    root.geometry(f"+{x}+{y}")
    root.attributes("-topmost", True)


def main():
    payload = payload_dir()
    root = tk.Tk()
    root.withdraw()
    info = {}

    def launch():
        try:
            start_hatari(payload, info)
        except Exception as e:  # noqa: BLE001 - shown to the user, there is no console
            messagebox.showerror(info["name"], f"Cannot start Hatari:\n{e}")
            root.destroy()

    try:
        info = json.loads((payload / "game.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        messagebox.showerror("Cannot start the game", f"Cannot read the game description:\n{e}")
        return
    try:
        if not info.get("splash"):
            raise ValueError("no splash image")
        show_splash(root, payload, info)
    except Exception:  # noqa: BLE001 - no (readable) image: start the game without a splash
        launch()
        return
    root.deiconify()
    root.after(HATARI_AFTER_MS, launch)
    root.after(SPLASH_MS, root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()
