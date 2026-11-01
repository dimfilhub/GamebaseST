"""Build a standalone executable for the current OS with PyInstaller (run: python build.py).

Needs: pip install pyinstaller pillow
The database and the data/hatari folder are copied next to the app; the (large) game data
folder is chosen by the user in Settings, or placed next to the app as data/.
"""
import plistlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

import PyInstaller.__main__

from standalone import StandaloneBuilder

NAME = "GamebaseST"
separator = ";" if sys.platform == "win32" else ":"
args = [
    "gamebaseST.py",
    "--name", NAME,
    "--windowed",
    "--noconfirm",
    "--add-data", f"images{separator}images",
    "--add-data", f"launcher{separator}launcher",
    "--add-data", f"README.md{separator}.",
]
# App icon: .ico on Windows, .icns on macOS (Linux binaries cannot embed one).
Path("build").mkdir(exist_ok=True)
icon = StandaloneBuilder._make_icon(Path("images/icon.png"), Path("build/app_icon"))
if icon:
    args += ["--icon", str(icon)]
if sys.platform != "darwin":  # Windows/Linux: single executable in dist/, next to the database
    args.append("--onefile")
PyInstaller.__main__.run(args)

if sys.platform == "darwin":
    # PyInstaller writes version 0.0.0 into Info.plist; use the app's own version instead.
    version = re.search(r'^APP_VERSION = "(.+)"', Path("ui/app.py").read_text(), re.M).group(1)
    app = Path("dist") / f"{NAME}.app"
    plist_path = app / "Contents" / "Info.plist"
    plist = plistlib.loads(plist_path.read_bytes())
    plist["CFBundleShortVersionString"] = plist["CFBundleVersion"] = version
    plist_path.write_bytes(plistlib.dumps(plist))
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)

# Ship the database and Hatari config/TOS next to the app, where DataLayout looks for them.
dist = Path("dist")
shutil.copy("atarist.sqlite3", dist / "atarist.sqlite3")
shutil.copytree("data/hatari", dist / "data" / "hatari", dirs_exist_ok=True)
