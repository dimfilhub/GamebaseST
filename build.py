"""Build a standalone executable for the current OS with PyInstaller (run: python build.py).

Needs: pip install pyinstaller pillow
The database and the data/hatari folder are copied next to the app; the (large) game data
folder is chosen by the user in Settings, or placed next to the app as data/.
"""
import shutil
import sys
from pathlib import Path

import PyInstaller.__main__

NAME = "GamebaseST"
separator = ";" if sys.platform == "win32" else ":"
args = [
    "gamebaseST.py",
    "--name", NAME,
    "--windowed",
    "--noconfirm",
    "--add-data", f"images{separator}images",
]
if sys.platform == "win32":
    args.append("--onefile")
PyInstaller.__main__.run(args)

# Ship the database and Hatari config/TOS next to the app, where DataLayout looks for them.
dist = Path("dist")
shutil.copy("atarist.sqlite3", dist / "atarist.sqlite3")
shutil.copytree("data/hatari", dist / "data" / "hatari", dirs_exist_ok=True)
