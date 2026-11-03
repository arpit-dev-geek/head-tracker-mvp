"""
Tkinter setup window: pick a monitor layout, then either type angle
thresholds directly ("Manual Adjust") or run the auto-detect-settle
calibration wizard ("Auto Calibrate"). "Start Tracking" saves whatever is
current and hands control back to the caller.
"""

import tkinter as tk
from tkinter import messagebox, ttk

import calibration_wizard
import config_store
import window_focus

MODEL_PATH = "face_landmarker.task"
EXIT_RATIO = 2 / 3

HEADING_FONT = ("Segoe UI", 11, "bold")
TITLE_FONT = ("Segoe UI", 14, "bold")
HINT_FONT = ("Segoe UI", 8)
ACCENT = "#2f6fed"
HINT_COLOR = "#777777"


def _enter_to_exit(enter_value):
    return enter_value * EXIT_RATIO


def _manual_fields(cfg):
    """Returns [(label, enter_key)] for whatever cfg['layout'] needs."""
    layout = cfg["layout"]
    if layout == "3":
        return [
            ("⬅  Turn LEFT threshold (deg, negative)", "yaw_left_enter"),
            ("➡  Turn RIGHT threshold (deg, positive)", "yaw_right_enter"),
            ("⬇  Tilt DOWN threshold (deg, negative)", "pitch_down_enter"),
        ]
    if layout == "2_side":
        side = cfg["side_zone"]
        side_key = "yaw_left_enter" if side == "LEFT" else "yaw_right_enter"
        side_icon = "⬅" if side == "LEFT" else "➡"
        return [
            (f"{side_icon}  Turn {side} threshold (deg)", side_key),
            ("⬇  Tilt DOWN threshold (deg, negative)", "pitch_down_enter"),
        ]
    if layout == "2_vertical":
        return [("⬆  Tilt UP threshold (deg, positive)", "pitch_top_enter")]
    raise RuntimeError(f"Unknown layout: {layout!r}")


class SetupUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Head Tracker Setup")
        self.resizable(False, False)

        try:
            style = ttk.Style(self)
            style.theme_use("vista")
            style.configure("Accent.TButton", font=("Segoe UI", 9, "bold"))
        except tk.TclError:
            pass

        self.cfg = config_store.load()

        starting_layout = self.cfg["layout"]
        self.mode_var = tk.StringVar(value="3" if starting_layout == "3" else "2")
        self.sub_var = tk.StringVar(value=starting_layout if starting_layout != "3" else "2_side")
        self.side_var = tk.StringVar(
            value=self.cfg.get("side_zone") or window_focus.detect_side_zone()
        )
        self.show_preview_var = tk.BooleanVar(value=self.cfg.get("show_preview", True))

        self._container = ttk.Frame(self, padding=20)
        self._container.pack(fill="both", expand=True)

        header = ttk.Frame(self._container)
        header.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))
        ttk.Label(header, text="\U0001f3af  Head Tracker Setup", font=TITLE_FONT).pack(anchor="w")
        ttk.Label(header, text="Pick how your screens are arranged, then set or calibrate thresholds.",
                  font=HINT_FONT, foreground=HINT_COLOR).pack(anchor="w", pady=(2, 0))

        ttk.Label(self._container, text="\U0001f5a5  1 · Choose your monitor layout",
                  font=HEADING_FONT, foreground=ACCENT).grid(row=1, column=0, columnspan=2, sticky="w")

        ttk.Radiobutton(self._container, text="\U0001f4bb↔\U0001f4bb  3-window setup",
                         variable=self.mode_var, value="3",
                         command=self._on_mode_pick).grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Radiobutton(self._container, text="\U0001f4bb↔\U0001f5a5  2-window setup",
                         variable=self.mode_var, value="2",
                         command=self._on_mode_pick).grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 0))

        self._sub_frame = ttk.Frame(self._container)
        self._sub_frame.grid(row=4, column=0, columnspan=2, sticky="w", padx=(26, 0))

        self._step2_frame = ttk.Frame(self._container)
        self._step2_frame.grid(row=5, column=0, columnspan=2, sticky="w", pady=(18, 0))

        self._fields_frame = None
        self._manual_vars = {}

        self._on_mode_pick()

    # ---- layout (step 1) ----

    def _get_layout(self):
        return "3" if self.mode_var.get() == "3" else self.sub_var.get()

    def _on_mode_pick(self):
        for child in self._sub_frame.winfo_children():
            child.destroy()

        if self.mode_var.get() == "2":
            ttk.Radiobutton(self._sub_frame, text="↔  Side-by-side (beside the laptop)",
                             variable=self.sub_var, value="2_side",
                             command=self._on_sub_pick).pack(anchor="w", pady=(4, 0))
            ttk.Radiobutton(self._sub_frame, text="↕  Vertical stack (above/below the laptop)",
                             variable=self.sub_var, value="2_vertical",
                             command=self._on_sub_pick).pack(anchor="w")

            if self.sub_var.get() == "2_side":
                side_frame = ttk.Frame(self._sub_frame)
                side_frame.pack(anchor="w", pady=(6, 0))
                ttk.Label(side_frame, text="External monitor is on the:").pack(side="left")
                ttk.Radiobutton(side_frame, text="⬅ Left", variable=self.side_var,
                                 value="LEFT", command=self._build_step2).pack(side="left", padx=(6, 0))
                ttk.Radiobutton(side_frame, text="➡ Right", variable=self.side_var,
                                 value="RIGHT", command=self._build_step2).pack(side="left", padx=(6, 0))

        self._build_step2()

    def _on_sub_pick(self):
        self._on_mode_pick()

    # ---- thresholds (step 2) ----

    def _current_layout_cfg(self):
        cfg = dict(self.cfg)
        cfg["layout"] = self._get_layout()
        cfg["side_zone"] = self.side_var.get()
        cfg["show_preview"] = self.show_preview_var.get()
        return cfg

    def _build_step2(self):
        for child in self._step2_frame.winfo_children():
            child.destroy()

        ttk.Separator(self._step2_frame, orient="horizontal").pack(fill="x", pady=(0, 10))
        ttk.Label(self._step2_frame, text="⚙  2 · Set thresholds",
                  font=HEADING_FONT, foreground=ACCENT).pack(anchor="w")

        btn_row = ttk.Frame(self._step2_frame)
        btn_row.pack(anchor="w", pady=(10, 8))
        ttk.Button(btn_row, text="✏  Manual Adjust", command=self._open_manual).pack(side="left", padx=(0, 8))
        ttk.Button(btn_row, text="\U0001f3af  Auto Calibrate", command=self._run_auto_calibrate).pack(side="left")

        self._fields_frame = ttk.Frame(self._step2_frame)
        self._fields_frame.pack(anchor="w", fill="x")
        self._manual_vars = {}

        ttk.Separator(self._step2_frame, orient="horizontal").pack(fill="x", pady=(12, 10))
        ttk.Checkbutton(self._step2_frame, text="\U0001f4f7  Show camera preview window while tracking",
                         variable=self.show_preview_var).pack(anchor="w", pady=(0, 10))
        ttk.Button(self._step2_frame, text="▶  Start Tracking",
                   command=self._start_tracking, style="Accent.TButton").pack(anchor="e")

    def _open_manual(self):
        for child in self._fields_frame.winfo_children():
            child.destroy()

        cfg = self._current_layout_cfg()
        fields = _manual_fields(cfg)
        self._manual_vars = {}
        for row, (label, key) in enumerate(fields):
            ttk.Label(self._fields_frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
            var = tk.StringVar(value=str(cfg.get(key, 0.0)))
            ttk.Entry(self._fields_frame, textvariable=var, width=10).grid(row=row, column=1, padx=(10, 0))
            self._manual_vars[key] = var

        ttk.Button(self._fields_frame, text="\U0001f4be  Save", command=self._save_manual).grid(
            row=len(fields), column=0, columnspan=2, pady=(10, 0), sticky="e"
        )

    def _save_manual(self):
        cfg = self._current_layout_cfg()
        try:
            for key, var in self._manual_vars.items():
                enter_value = float(var.get())
                cfg[key] = enter_value
                cfg[key.replace("_enter", "_exit")] = _enter_to_exit(enter_value)
        except ValueError:
            messagebox.showerror("Invalid input", "Angles must be numbers.")
            return

        self.cfg = config_store.save(cfg)
        messagebox.showinfo("Saved", "Thresholds saved.")

    def _run_auto_calibrate(self):
        cfg = self._current_layout_cfg()
        self.withdraw()
        try:
            captured = calibration_wizard.run(cfg, model_path=MODEL_PATH)
        except Exception as exc:
            self.deiconify()
            messagebox.showerror("Calibration failed", str(exc))
            return
        self.deiconify()

        if captured is None:
            messagebox.showinfo("Cancelled", "Calibration was cancelled - nothing saved.")
            return

        for zone, value in captured.items():
            if zone == "LEFT":
                cfg["yaw_left_enter"], cfg["yaw_left_exit"] = value, _enter_to_exit(value)
            elif zone == "RIGHT":
                cfg["yaw_right_enter"], cfg["yaw_right_exit"] = value, _enter_to_exit(value)
            elif zone == "LAPTOP":
                cfg["pitch_down_enter"], cfg["pitch_down_exit"] = value, _enter_to_exit(value)
            elif zone == "TOP":
                cfg["pitch_top_enter"], cfg["pitch_top_exit"] = value, _enter_to_exit(value)

        self.cfg = config_store.save(cfg)
        messagebox.showinfo(
            "Calibrated",
            "Calibration saved. The measured angles are now shown below - "
            "adjust and hit Save if any of them need a tweak."
        )
        self._open_manual()

    def _start_tracking(self):
        cfg = self._current_layout_cfg()
        self.cfg = config_store.save(cfg)
        self.destroy()


def run():
    """Opens the setup window; blocks until the user clicks Start Tracking.
    Returns the config to run the tracker with."""
    app = SetupUI()
    app.mainloop()
    return config_store.load()
