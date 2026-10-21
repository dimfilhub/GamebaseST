import tkinter as tk
from tkinter import ttk

from ui.style import BACKGROUND_COLOR

NOTICE = ("EmuTOS is free software and may be shared freely.\n\n"
          "The original Atari TOS and most Atari ST games are still protected by copyright. "
          "If you choose the original TOS, or share an app containing a game you do not have "
          "the rights to, you do so entirely at your own risk: you have full responsibility for "
          "complying with copyright law. The author of GamebaseST accepts no responsibility.")


class StandaloneDialog(tk.Toplevel):
    """Asks which TOS to bundle. `result` is "emutos", "real" or None when cancelled."""

    def __init__(self, parent, real_available):
        super().__init__(parent)
        self.title("Standalone app")
        self.configure(background=BACKGROUND_COLOR)
        self.transient(parent)
        self.resizable(False, False)
        self.result = None

        box = ttk.LabelFrame(self, text="Operating system (TOS) to include", padding=10)
        box.pack(fill="x", padx=10, pady=10)
        self.choice = tk.StringVar(self, value="emutos")
        ttk.Radiobutton(box, text="EmuTOS (free, recommended)", variable=self.choice,
                        value="emutos").pack(anchor="w")
        real = ttk.Radiobutton(box, text="Original Atari TOS (your data/hatari/tos.img)",
                               variable=self.choice, value="real")
        real.pack(anchor="w", pady=(4, 0))
        if not real_available:
            real.state(["disabled"])

        ttk.Label(self, text="Copyright", font=("TkDefaultFont", 0, "bold")).pack(anchor="w", padx=10)
        ttk.Label(self, text=NOTICE, wraplength=420, justify="left").pack(anchor="w", padx=10, pady=(2, 10))

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ok = ttk.Button(buttons, text="I understand, continue", command=self._ok)
        ok.pack(side="right", padx=(0, 5))
        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())
        self.grab_set()
        ok.focus_set()

    def _ok(self):
        self.result = self.choice.get()
        self.destroy()
