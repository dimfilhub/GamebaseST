"""Finding Hatari, preparing disk images and launching games."""
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

from config import Config
from data_layout import DataLayout


# Hatari key names (SDL) for the keyboard-emulated joystick.
JOYSTICK_ACTIONS = (("kUp", "Up"), ("kDown", "Down"), ("kLeft", "Left"),
                    ("kRight", "Right"), ("kFire", "Fire"))
DEFAULT_JOYSTICK_KEYS = {"kUp": "Up", "kDown": "Down", "kLeft": "Left",
                         "kRight": "Right", "kFire": "Space"}
CONTROLLERS = ("keyboard", "joystick")


def load_controller_settings(config: Config):
    """(controller, joystick_keys) from config.json, with defaults filled in."""
    controller = config.get("controller", "keyboard")
    if controller not in CONTROLLERS:
        controller = "keyboard"
    saved = config.get("joystick_keys", {}) or {}
    keys = {a: saved.get(a) or d for a, d in DEFAULT_JOYSTICK_KEYS.items()}
    return controller, keys


class LaunchError(Exception):
    """Raised when a game cannot be launched; the message is user-facing."""


class HatariLocator:
    def __init__(self, layout: DataLayout, config: Config):
        self.layout = layout
        self.config = config

    @staticmethod
    def normalize(p):
        """Accept a Hatari.app bundle and return the real executable inside it."""
        p = Path(p)
        if p.suffix == ".app":
            p = p / "Contents" / "MacOS" / "hatari"
        return p

    def find(self):
        """Locate the Hatari executable: env var, saved config, PATH, usual places."""
        candidates = [os.environ.get("HATARI_PATH"), self.config.get("hatari"),
                      self.layout.hatari_dir / "hatari.exe", shutil.which("hatari"),
                      "/Applications/Hatari.app",
                      "/opt/homebrew/bin/hatari",
                      "/usr/local/bin/hatari",
                      r"C:\Program Files\Hatari\hatari.exe",
                      r"C:\Program Files (x86)\Hatari\hatari.exe"]
        for c in candidates:
            if c and self.normalize(c).is_file():
                return self.normalize(c)
        return None

    def remember(self, path):
        """Validate and persist a user-chosen executable; returns it or None."""
        exe = self.normalize(path)
        if not exe.is_file():
            return None
        self.config.set("hatari", str(exe))
        return exe


class DiskPreparer:
    DISK_EXTS = {".st", ".msa", ".stx", ".dim", ".ipf", ".ctr", ".raw"}

    def __init__(self, layout: DataLayout):
        self.layout = layout

    def prepare(self, ga_id, zip_path, file_to_run):
        """Extract the game's disk image(s) from its zip into data/cache/run/{id}.
        Returns a list of 1-2 disk image paths (disk A, optional disk B).
        Extracting by basename only avoids any path-traversal from zip entries."""
        run_dir = self.layout.cache / "run" / str(ga_id)
        shutil.rmtree(run_dir, ignore_errors=True)
        run_dir.mkdir(parents=True)
        with zipfile.ZipFile(zip_path) as z:
            members = [i for i in z.infolist() if not i.is_dir()]
            images = sorted((i for i in members if Path(i.filename).suffix.lower() in self.DISK_EXTS),
                            key=lambda i: i.filename.lower())
            wanted = None
            if file_to_run:
                wanted = next((i for i in members
                               if Path(i.filename).name.lower() == Path(file_to_run).name.lower()
                               and Path(i.filename).suffix.lower() in self.DISK_EXTS), None)
            chosen = [wanted] if wanted else images[:2]
            if not chosen:
                raise ValueError("No disk image (.st/.msa/.stx/...) found in the zip.")
            out = []
            for info in chosen:
                target = run_dir / Path(info.filename).name
                with z.open(info) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                out.append(target)
        return out


class HatariLauncher:
    def __init__(self, layout: DataLayout, preparer: DiskPreparer, config: Config):
        self.layout = layout
        self.preparer = preparer
        self.config = config  # controller and joystick keys are read on every launch

    def _config_with_keys(self, keys):
        """Hatari config with `keys` applied to [Joystick1]. A copy is written to the cache
        so the user's atari_keys file stays untouched."""
        src = self.layout.hatari_config
        if keys == DEFAULT_JOYSTICK_KEYS or not src.is_file():
            return src
        lines = src.read_text(encoding="utf-8", errors="surrogateescape").splitlines(keepends=True)
        section = None
        for i, line in enumerate(lines):
            s = line.strip()
            if s.startswith("["):
                section = s.casefold()
            elif section == "[joystick1]" and "=" in s:
                name = s.split("=", 1)[0].strip()
                if name in keys:
                    lines[i] = f"{name} = {keys[name]}\n"
        out = self.layout.cache / "hatari_run.cfg"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("".join(lines), encoding="utf-8", errors="surrogateescape")
        return out

    def launch(self, hatari, game, zip_path, file_to_run):
        try:
            disks = self.preparer.prepare(game.id, zip_path, file_to_run)
        except (zipfile.BadZipFile, ValueError, OSError) as e:
            raise LaunchError(f"{game.name}\n\n{e}") from e
        if not self.layout.tos_image.is_file():
            raise LaunchError(f"TOS image not found:\n{self.layout.tos_image}")
        # Same setup as the atari-compilation-disks project
        controller, keys = load_controller_settings(self.config)
        cmd = [
            str(hatari), "--joy1", "keys" if controller == "keyboard" else "real",
            "--configfile", str(self._config_with_keys(keys)),
            "--tos", str(self.layout.tos_image),
            "--machine", "st", "--monitor", "tv", "--fullscreen", "--memsize", "1",
            "--statusbar", "FALSE", "--drive-led", "TRUE", "--confirm-quit", "FALSE",
            "--disk-a", str(disks[0]),
        ]
        if len(disks) > 1:
            cmd += ["--disk-b", str(disks[1])]
        try:
            subprocess.Popen(cmd, cwd=disks[0].parent)
        except OSError as e:
            raise LaunchError(str(e)) from e
