"""Extract the zips in sources/ into the data/ tree.

Usage: python3 populate.py [--dry-run]
"""
import sys
import zipfile
from pathlib import Path

from data_layout import DataLayout


class Populator:
    """Existing files with the same size are skipped, so it can be re-run safely."""

    def __init__(self, layout: DataLayout, log=print):
        self.layout = layout
        self.log = log  # callable(str) receiving progress lines

    @property
    def plan(self):
        """zip name -> (zip-internal prefix to strip, destination folder).
        Entries outside the prefix (e.g. "Music Players/") are ignored."""
        l = self.layout
        return {
            "GAMES-ST.zip":            ("ST/",         l.games / "ST"),
            "GAMES-Automation.zip":    ("Automation/", l.games / "Automation"),
            "GAMES-DBUG.zip":          ("DBUG/",       l.games / "DBUG"),
            "Screenshots (all).zip":   ("Screenshots/", l.screenshots),
            "MUSIC.zip":               ("Music/",      l.music_dir),
            "Extras.zip":              ("",            l.extras_dir),
            "Extras-Instructions.zip": ("",            l.extras_dir),
            "Extras-HardDisk.zip":     ("HardDisk/",   l.extras_runnable / "HardDisk"),
            "EXTRAS-HDOLD.zip":        ("HDOLD/",      l.extras_runnable / "HDOLD"),
            "EXTRAS-stx(oldpack).zip": ("stx/",        l.extras_runnable / "STX"),
        }

    def check_sources(self, folder=None):
        """Compare `folder` (default: the sources folder) with the zips the plan expects.
        Returns (found, missing, broken, extra) lists of zip names."""
        folder = Path(folder or self.layout.sources)
        present = {p.name for p in folder.iterdir() if p.is_file()} if folder.is_dir() else set()
        expected = list(self.plan)
        found = [n for n in expected if n in present]
        broken = [n for n in found if not zipfile.is_zipfile(folder / n)]
        found = [n for n in found if n not in broken]
        missing = [n for n in expected if n not in present]
        extra = sorted(n for n in present - set(expected) if n.lower().endswith(".zip"))
        return found, missing, broken, extra

    def extract(self, zip_path, prefix, dest, dry=False):
        n = skipped = 0
        with zipfile.ZipFile(zip_path) as z:
            for info in z.infolist():
                name = info.filename
                if info.is_dir() or name.startswith("__MACOSX") or name.endswith(".DS_Store"):
                    continue
                if not name.startswith(prefix):
                    continue
                rel = Path(name[len(prefix):])
                target = (dest / rel).resolve()
                if dest.resolve() not in target.parents:  # zip-slip guard
                    self.log(f"  skip unsafe path: {name}")
                    continue
                if target.exists() and target.stat().st_size == info.file_size:
                    skipped += 1
                    continue
                n += 1
                if not dry:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(info) as src, open(target, "wb") as out:
                        while chunk := src.read(1 << 20):
                            out.write(chunk)
        return n, skipped

    def run(self, dry=False):
        for zname, (prefix, dest) in self.plan.items():
            zp = self.layout.sources / zname
            if not zp.exists():
                self.log(f"missing: {zname}")
                continue
            n, s = self.extract(zp, prefix, dest, dry)
            self.log(f"{zname}: {'would extract' if dry else 'extracted'} {n}, skipped {s}")


if __name__ == "__main__":
    Populator(DataLayout()).run(dry="--dry-run" in sys.argv)
