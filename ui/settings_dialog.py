import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from data_layout import DataLayout
from hatari import CONTROLLERS, DEFAULT_JOYSTICK_KEYS, JOYSTICK_ACTIONS, load_controller_settings
from ui.style import BACKGROUND_COLOR

# Tk keysym (lowercase) -> Hatari/SDL key name
KEY_NAMES = {
    "space": "Space", "control_l": "Left Ctrl", "control_r": "Right Ctrl",
    "shift_l": "Left Shift", "shift_r": "Right Shift", "alt_l": "Left Alt", "alt_r": "Right Alt",
    "return": "Return", "tab": "Tab", "backspace": "Backspace", "up": "Up", "down": "Down",
    "left": "Left", "right": "Right", "insert": "Insert", "delete": "Delete", "home": "Home",
    "end": "End", "prior": "PageUp", "next": "PageDown",
}


def sdl_key_name(event):
    """Translate a Tk key event to a Hatari/SDL key name, or None if unsupported."""
    keysym = event.keysym
    if keysym.casefold() in KEY_NAMES:
        return KEY_NAMES[keysym.casefold()]
    if keysym.startswith("KP_") and keysym[3:].isdigit():
        return f"Keypad {keysym[3:]}"
    if len(keysym) == 1 and keysym.isalnum():
        return keysym.upper()
    if len(keysym) > 1 and keysym[0] == "F" and keysym[1:].isdigit():
        return keysym
    return None


class SettingsDialog(tk.Toplevel):
    """Controller (keyboard / joystick), Hatari joystick keys and the data folder."""

    def __init__(self, parent, layout, config, on_data_changed=None, on_populate=None, locator=None):
        super().__init__(parent)
        self.title("Settings")
        self.configure(background=BACKGROUND_COLOR)
        self.transient(parent)
        self.resizable(False, False)
        self.layout, self.config, self.on_data_changed = layout, config, on_data_changed
        self.locator = locator
        self.on_populate = on_populate  # opens the Populate folders window
        controller, keys = load_controller_settings(config)

        box = ttk.LabelFrame(self, text="Controller", padding=10)
        box.pack(fill="x", padx=10, pady=10)
        self.controller = tk.StringVar(self, value=controller)
        for label, value in zip(("Keyboard", "Joystick"), CONTROLLERS):
            ttk.Radiobutton(box, text=label, variable=self.controller,
                            value=value).pack(side="left", padx=(0, 15))

        self.key_vars, self._capturing = {}, {}
        kf = ttk.LabelFrame(self, text="Keyboard joystick keys (Hatari)", padding=10)
        kf.pack(fill="x", padx=10, pady=(0, 10))
        for row, (action, label) in enumerate(JOYSTICK_ACTIONS):
            self.key_vars[action] = tk.StringVar(self, value=keys[action])
            ttk.Label(kf, text=label + ":").grid(row=row, column=0, sticky="w", pady=2)
            ttk.Entry(kf, textvariable=self.key_vars[action], width=14,
                      state="readonly").grid(row=row, column=1, padx=5, pady=2)
            b = ttk.Button(kf, text="Set...")
            b.configure(command=lambda a=action, btn=b: self._capture(a, btn))
            b.grid(row=row, column=2, pady=2)
        ttk.Button(kf, text="Defaults", command=self._default_keys).grid(
            row=len(JOYSTICK_ACTIONS), column=0, columnspan=3, sticky="e", pady=(5, 0))

        hf = ttk.LabelFrame(self, text="Hatari executable (or Hatari.app)", padding=10)
        hf.pack(fill="x", padx=10, pady=(0, 10))
        found = locator.find() if locator else None
        self.hatari_var = tk.StringVar(self, value=str(found) if found else "")
        ttk.Entry(hf, textvariable=self.hatari_var, width=50).grid(row=0, column=0, sticky="ew")
        ttk.Button(hf, text="Browse...", command=self._browse_hatari).grid(row=0, column=1, padx=(5, 0))
        hf.columnconfigure(0, weight=1)

        df = ttk.LabelFrame(self, text="Data folder (already populated)", padding=10)
        df.pack(fill="x", padx=10, pady=(0, 10))
        self.data_var = tk.StringVar(self, value=str(layout.data))
        ttk.Entry(df, textvariable=self.data_var, width=50).grid(row=0, column=0, sticky="ew")
        ttk.Button(df, text="Browse...", command=self._browse_data).grid(row=0, column=1, padx=(5, 0))
        ttk.Button(df, text="Default", command=lambda: self.data_var.set(
            str(layout.root / "data"))).grid(row=0, column=2, padx=(5, 0))
        df.columnconfigure(0, weight=1)

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(bar, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(bar, text="Save", command=self._save).pack(side="right", padx=(0, 5))
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()

    def _default_keys(self):
        self._stop_capture()
        for action, var in self.key_vars.items():
            var.set(DEFAULT_JOYSTICK_KEYS[action])

    def _stop_capture(self):
        if self._capturing:
            self.unbind("<KeyPress>", self._capturing.pop("binding"))
            self._capturing.pop("button").configure(text="Set...")

    def _capture(self, action, button):
        """Wait for the next key press and assign it to the joystick `action`."""
        self._stop_capture()
        button.configure(text="Press a key")
        self.focus_set()

        def on_key(event):
            name = sdl_key_name(event)
            if name:
                self.key_vars[action].set(name)
            self._stop_capture()
            return "break"

        self._capturing["button"] = button
        self._capturing["binding"] = self.bind("<KeyPress>", on_key)

    def _browse_data(self):
        d = filedialog.askdirectory(parent=self, title="Select the populated data folder",
                                    initialdir=self.data_var.get(), mustexist=True)
        if d:
            self.data_var.set(d)

    def _browse_hatari(self):
        p = filedialog.askopenfilename(parent=self, title="Select the Hatari executable (or Hatari.app)")
        if not p and sys.platform == "darwin":
            # macOS .app bundles are directories
            p = filedialog.askdirectory(parent=self, title="Select Hatari.app")
        if p:
            self.hatari_var.set(p)

    @staticmethod
    def _folder_problem(data):
        """Describe what is wrong with a data folder, or None if it is complete and populated."""
        probe = DataLayout(data=data)
        if not all(d.is_dir() for d in probe.all_dirs):
            return "does not have the correct folder structure"
        if not any(p.is_file() for p in probe.games.rglob("*")):
            return "has no game files (it is not populated)"
        return None

    def _save(self):
        data = Path(self.data_var.get().strip() or self.layout.root / "data").expanduser()
        changed = data != self.layout.data
        populate = False
        problem = self._folder_problem(data) if changed else None
        if problem:
            answer = messagebox.askyesnocancel(
                "Data folder needs setting up",
                f"The selected data folder {problem}:\n{data}\n\n"
                "Yes: use it and open the Populate folders window to create/populate it\n"
                "No: use it as it is\nCancel: go back",
                parent=self)
            if answer is None:
                return
            populate = answer
        hatari = self.hatari_var.get().strip()
        if hatari and self.locator and not self.locator.remember(hatari):
            messagebox.showerror("Hatari", f"Not an executable file:\n{hatari}", parent=self)
            return
        try:
            self.config.set("controller", self.controller.get())
            self.config.set("joystick_keys", {a: v.get() for a, v in self.key_vars.items()})
            if changed:
                self.layout.set_data(data)
        except OSError as e:
            messagebox.showerror("Could not save settings", str(e), parent=self)
            return
        self.destroy()
        if changed and self.on_data_changed:
            self.on_data_changed()
        if populate and self.on_populate:
            self.on_populate()
