"""Build a self-contained app (Hatari + EmuTOS + one game) that anyone can run.

The launcher (launcher/standalone_launcher.py: splash screen, then Hatari) is frozen with
PyInstaller for the operating system we are running on; Hatari, EmuTOS and the game are then
copied into its `payload` folder. PyInstaller cannot cross-compile: build on the OS you target."""
import importlib.util
import json
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from config import Config
from data_layout import RESOURCE_ROOT, DataLayout
from hatari import (HATARI_OPTIONS, DiskPreparer, config_with_keys, joystick_option,
                    load_controller_settings)

LAUNCHER_SRC = RESOURCE_ROOT / "launcher" / "standalone_launcher.py"
IS_MAC, IS_WINDOWS = sys.platform == "darwin", sys.platform == "win32"
ICON_SIZES = (16, 32, 128, 256, 512)
EMUTOS_DIRS = ("/usr/share/hatari", "/usr/local/share/hatari",
               "/usr/share/emutos", "/usr/local/share/emutos")

TOS_LINES = {
    "emutos": "EmuTOS   https://emutos.sourceforge.io/ (GNU GPL v2 or later), saved as tos.img\n"
              "EmuTOS is free software; its source code is available from the site above.",
    "real": "tos.img  An original Atari TOS ROM, which is copyrighted. It was added by the person\n"
            "who made this app, who is solely responsible for having the right to distribute it.",
}

ABOUT = """\
This app bundles the Hatari Atari ST emulator, a TOS image and one game.

Hatari   https://hatari.tuxfamily.org/  (GNU GPL v2 or later)
{tos_line}
Hatari is free software; its source code is available from the site above.

Created with GamebaseST Browser and Player.
Game saves and the Hatari configuration are kept in the folder named {bundle_id}
inside your user data folder (~/Library/Application Support, %APPDATA% or ~/.local/share).
"""


class StandaloneError(Exception):
    """Raised when the app cannot be built; the message is user-facing."""


def _run(cmd, **kwargs):
    try:
        r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kwargs)
    except OSError as e:
        raise StandaloneError(f"Cannot run {cmd[0]}:\n{e}") from e
    if r.returncode:
        tail = "\n".join((r.stderr or r.stdout).strip().splitlines()[-15:])
        raise StandaloneError(f"{Path(str(cmd[0])).name} failed:\n{tail}")


def app_name(game):
    """File-system safe name of the game's app."""
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', " ", game.name)
    return re.sub(r"\s+", " ", name).strip(" .")[:80] or f"Game {game.id}"


def bundle_id(game):
    slug = re.sub(r"[^a-z0-9]+", "-", game.name.casefold()).strip("-")[:40] or "game"
    return f"com.gamebasest.{slug}-{game.id}"


def is_emutos(path):
    return path.is_file() and b"EmuTOS" in path.read_bytes()


def pyinstaller_command():
    """Command that runs PyInstaller: this interpreter's module, else `pyinstaller` on PATH."""
    if not getattr(sys, "frozen", False) and importlib.util.find_spec("PyInstaller"):
        return [sys.executable, "-m", "PyInstaller"]
    exe = shutil.which("pyinstaller")
    if exe:
        return [exe]
    raise StandaloneError("PyInstaller is needed to build the app.\n"
                          "Install it with:  pip install pyinstaller pillow\n"
                          "(and run GamebaseST from that Python environment).")


class StandaloneBuilder:
    def __init__(self, layout: DataLayout, preparer: DiskPreparer, config: Config):
        self.layout = layout
        self.preparer = preparer
        self.config = config

    def app_path(self, dest_dir, game):
        """macOS: <name>.app. Windows/Linux: a <name> folder with the executable in it."""
        return Path(dest_dir) / (f"{app_name(game)}.app" if IS_MAC else app_name(game))

    def build(self, hatari, game, zip_path, file_to_run, dest_dir, splash=None, icon=None,
              tos="emutos"):
        """Create the app for this operating system in `dest_dir` and return its path.
        `splash` and `icon` are optional image files. `tos` is "emutos" (free, default) or "real"
        (your data/hatari/tos.img: you are responsible for the right to distribute it).
        An existing app of the name is replaced."""
        hatari = Path(hatari).resolve()
        runtime = self._runtime_source(hatari)
        tos_image = self._tos_image(hatari, tos)
        pyinstaller = pyinstaller_command()
        try:
            disks = self.preparer.prepare(game.id, zip_path, file_to_run)
        except (zipfile.BadZipFile, ValueError, OSError) as e:
            raise StandaloneError(f"{game.name}\n\n{e}") from e

        controller, keys = load_controller_settings(self.config)
        name, ident = app_name(game), bundle_id(game)
        work = Path(tempfile.mkdtemp(prefix="standalone-", dir=self._cache()))
        try:
            payload = work / "payload"
            hatari_rel = self._copy_runtime(runtime, hatari, payload / "hatari")
            (payload / "disks").mkdir()
            for d in disks:
                shutil.copy2(d, payload / "disks" / d.name)
            shutil.copy2(tos_image, payload / "tos.img")
            cfg = self.layout.hatari_config
            (payload / "hatari.cfg").write_text(
                config_with_keys(cfg, keys) if cfg.is_file() else "",
                encoding="utf-8", errors="surrogateescape")
            splash_name = None
            if splash and Path(splash).is_file():
                splash_name = "splash" + Path(splash).suffix.lower()
                shutil.copy2(splash, payload / splash_name)
            (payload / "game.json").write_text(json.dumps({
                "name": game.name, "id": ident, "hatari": f"hatari/{hatari_rel}",
                "splash": splash_name, "disks": [d.name for d in disks],
                "args": [*joystick_option(controller), *HATARI_OPTIONS],
            }, indent=2), encoding="utf-8")
            (payload / "ABOUT.txt").write_text(ABOUT.format(tos_line=TOS_LINES[tos], bundle_id=ident), encoding="utf-8")

            built = self._freeze_launcher(pyinstaller, work, name, ident, icon or splash)
            target = built / "Contents" / "Resources" if IS_MAC else built
            shutil.move(str(payload), target / "payload")
            if IS_MAC:
                # The bundle changed after PyInstaller signed it. No --deep: the frameworks of
                # the bundled Hatari.app keep their own signatures.
                _run(["xattr", "-cr", built])
                _run(["codesign", "--force", "--sign", "-", built])

            final = self.app_path(dest_dir, game)
            try:
                Path(dest_dir).mkdir(parents=True, exist_ok=True)
                if final.exists():
                    shutil.rmtree(final)
                shutil.move(str(built), final)
            except OSError as e:
                raise StandaloneError(f"Cannot write {final}:\n{e}") from e
            return final
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _cache(self):
        cache = self.layout.cache / "standalone"
        cache.mkdir(parents=True, exist_ok=True)
        return cache

    # ---------- Hatari and EmuTOS ----------
    @staticmethod
    def _runtime_source(hatari):
        """What to copy to get a working Hatari: the .app (macOS), the install folder (Windows,
        its DLLs sit next to hatari.exe) or the single binary (Linux, which needs the system's SDL2)."""
        if IS_MAC:
            for p in hatari.parents:
                if p.suffix == ".app":
                    return p
            raise StandaloneError("A standalone app needs the Hatari.app bundle, not a bare "
                                  "executable.\nSelect Hatari.app in Settings.")
        return hatari.parent if IS_WINDOWS else hatari

    def _tos_image(self, hatari, tos):
        """The image to bundle: your own data/hatari/tos.img ("real"), or a free EmuTOS one."""
        if IS_MAC:  # Hatari.app is copied as it is, with the tos.img inside it
            inner = self._runtime_source(hatari) / "Contents" / "Resources" / "tos.img"
            if inner.is_file() and not is_emutos(inner):
                raise StandaloneError(f"{inner}\nis not EmuTOS. Install the official Hatari for "
                                      "macOS, which includes EmuTOS.")
        if tos == "real":
            if not self.layout.tos_image.is_file():
                raise StandaloneError(f"TOS image not found:\n{self.layout.tos_image}")
            return self.layout.tos_image
        return self._find_emutos(hatari)

    def _find_emutos(self, hatari):
        """A free EmuTOS image: data/hatari/emutos.img, else the one shipped with Hatari."""
        found = [self.layout.hatari_dir / "emutos.img"]
        if IS_MAC:
            found.append(self._runtime_source(hatari) / "Contents" / "Resources" / "tos.img")
        else:
            for d in (hatari.parent, *map(Path, EMUTOS_DIRS)):
                found += [d / "tos.img", *sorted(d.glob("etos*.img")), *sorted(d.glob("emutos*.img"))]
        for p in found:
            if is_emutos(p):
                return p
        raise StandaloneError("No EmuTOS image found.\nDownload one from https://emutos.sourceforge.io/ "
                              f"and save it as\n{self.layout.hatari_dir / 'emutos.img'}")

    @staticmethod
    def _copy_runtime(source, hatari, dest):
        """Copy Hatari into dest; returns the executable's path inside dest. ROM images are left
        out (the EmuTOS one is added separately), so a real TOS can never end up in the app."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        if IS_MAC:
            try:
                exe = plistlib.loads((source / "Contents" / "Info.plist").read_bytes())["CFBundleExecutable"]
            except (OSError, ValueError, KeyError) as e:
                raise StandaloneError(f"{source} is not a valid Hatari.app:\n{e}") from e
            _run(["ditto", source, dest / source.name])
            return f"{source.name}/Contents/MacOS/{exe}"
        if source.is_dir():
            shutil.copytree(source, dest, symlinks=True,
                            ignore=shutil.ignore_patterns("*.img", "*.rom", "*.cfg", "atari_keys"))
            return hatari.relative_to(source).as_posix()
        dest.mkdir()
        shutil.copy2(source, dest / source.name)
        return source.name

    # ---------- the PyInstaller launcher ----------
    def _freeze_launcher(self, pyinstaller, work, name, ident, icon_image):
        if not LAUNCHER_SRC.is_file():
            raise StandaloneError(f"Launcher source missing:\n{LAUNCHER_SRC}")
        cmd = [*pyinstaller, "--noconfirm", "--clean", "--onedir", "--windowed",
               "--name", name, "--distpath", work / "dist", "--workpath", work / "build",
               "--specpath", work / "spec", "--log-level", "WARN"]
        icon = self._make_icon(icon_image, work / "icon") if icon_image else None
        if icon:
            cmd += ["--icon", icon]
        if IS_MAC:
            cmd += ["--osx-bundle-identifier", ident]
        _run([*cmd, LAUNCHER_SRC], cwd=work)
        built = work / "dist" / (f"{name}.app" if IS_MAC else name)
        if not built.exists():
            raise StandaloneError("PyInstaller did not produce the app.")
        return built

    @staticmethod
    def _make_icon(image, stem):
        """An .icns (macOS) or .ico (Windows) made from `image`; None elsewhere or on failure."""
        if not (IS_MAC or IS_WINDOWS):
            return None
        try:
            from PIL import Image, ImageOps
            with Image.open(image) as im:
                fitted = ImageOps.contain(im.convert("RGBA"), (1024, 1024))
            square = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
            square.paste(fitted, ((1024 - fitted.width) // 2, (1024 - fitted.height) // 2))
            if IS_WINDOWS:
                out = stem.with_suffix(".ico")
                square.save(out, sizes=[(s, s) for s in (16, 32, 48, 64, 128, 256)])
                return out
            out = stem.with_suffix(".icns")
            with tempfile.TemporaryDirectory() as tmp:
                iconset = Path(tmp) / "game.iconset"
                iconset.mkdir()
                for size in ICON_SIZES:
                    for scale, suffix in ((1, ""), (2, "@2x")):
                        px = size * scale
                        square.resize((px, px), Image.LANCZOS).save(
                            iconset / f"icon_{size}x{size}{suffix}.png")
                _run(["iconutil", "-c", "icns", iconset, "-o", out])
            return out
        except (OSError, ValueError, StandaloneError):
            return None
