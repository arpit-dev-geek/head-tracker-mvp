"""
Head-position monitor-zone visualizer and window-focus switcher.

Shows your webcam feed with live yaw/pitch angles and which zone your head
is currently pointed at. When window-switching is enabled, turning your
head toward a zone restores keyboard focus to whatever window you last
used on that monitor (Windows-only, requires pywin32).

Run this directly: it opens a setup window first (pick your monitor
layout, then Manual Adjust or Auto Calibrate your thresholds), then starts
tracking once you click "Start Tracking". A small always-on-top control
panel accompanies the webcam preview with Pause/Resume and Close Tracking
buttons. Requires the FaceLandmarker model file (see README.md for the
download command).

Controls:
    q or ESC (in the webcam window, if shown)  -> close tracking
"""

import time
import tkinter as tk
from tkinter import ttk

import cv2

import calibration_ui
import head_pose
import zone_classifier

try:
    import window_focus
except ImportError:
    window_focus = None

MODEL_PATH = "face_landmarker.task"
CAM_INDEX = 0

# How long (seconds) a candidate zone must hold before it's "confirmed"
DWELL_SECONDS = 0.3

# Smoothing factor for the exponential moving average (0 < alpha <= 1).
EMA_ALPHA = 0.3

PREVIEW_WINDOW_TITLE = "Head Zone Tracker"
CONTROL_PANEL_TITLE = "Tracker Control"

# Windows-only: move keyboard focus to the zone's last-focused window
# whenever the CONFIRMED ZONE changes. Requires pywin32.
ENABLE_WINDOW_SWITCHING = True

ZONE_ICONS = {"LEFT": "⬅", "RIGHT": "➡", "LAPTOP": "\U0001f4bb", "TOP": "⬆"}

# User-facing zone names - "LEFT"/"RIGHT"/"TOP" are internal (shared with
# zone_classifier/window_focus); the single external monitor in a 2-window
# layout is always "Monitor 1" regardless of which physical side/direction
# it's on, and the laptop screen is always "Laptop".
ZONE_DISPLAY = {"LEFT": "Monitor 1", "RIGHT": "Monitor 2", "TOP": "Monitor 1", "LAPTOP": "Laptop"}


def _display_zone(zone):
    return ZONE_DISPLAY.get(zone, zone)


TRACKING_COLOR = "#1a9c4a"
PAUSED_COLOR = "#c77a00"


class TrackerControlPanel(tk.Tk):
    """Always-on-top companion window to the webcam preview: shows the
    current status/zone and lets you pause or close tracking without
    clicking into the cv2 window. Drives the whole capture loop itself via
    `after()` instead of a blocking `while True`, so the UI stays live."""

    def __init__(self, cfg):
        super().__init__()
        self.title(CONTROL_PANEL_TITLE)
        self.resizable(False, False)
        self.attributes("-topmost", True)

        try:
            style = ttk.Style(self)
            style.theme_use("vista")
        except tk.TclError:
            pass

        self.cfg = cfg
        self.show_preview = cfg.get("show_preview", True)
        self.rules, self.fallback_zone = zone_classifier.build_rules(cfg)
        self.stream = head_pose.HeadPoseStream(
            MODEL_PATH, cam_index=CAM_INDEX,
            yaw_sign=cfg["yaw_sign"], pitch_sign=cfg["pitch_sign"], ema_alpha=EMA_ALPHA,
        )

        self.focus_mgr = None
        if ENABLE_WINDOW_SWITCHING:
            if window_focus is None:
                raise RuntimeError(
                    "ENABLE_WINDOW_SWITCHING is True but pywin32 isn't installed. "
                    "Run `pip install pywin32` or set ENABLE_WINDOW_SWITCHING = False."
                )
            zone_monitor_map = window_focus.build_zone_monitor_map(cfg["layout"])
            self.focus_mgr = window_focus.WindowFocusManager(
                zone_monitor_map, [PREVIEW_WINDOW_TITLE, CONTROL_PANEL_TITLE]
            )
            self.focus_mgr.seed_from_current_windows()

        self.confirmed_zone = self.fallback_zone
        self.candidate_zone = self.fallback_zone
        self.candidate_since = None
        self.paused = False
        self._closing = False

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(10, self._step)

    def _build_ui(self):
        pad = ttk.Frame(self, padding=16)
        pad.pack(fill="both", expand=True)

        ttk.Label(pad, text="\U0001f3af  Head Zone Tracker",
                  font=("Segoe UI", 13, "bold")).pack(anchor="w")

        self.status_var = tk.StringVar(value="●  Tracking")
        self.status_label = ttk.Label(pad, textvariable=self.status_var,
                                       font=("Segoe UI", 11, "bold"), foreground=TRACKING_COLOR)
        self.status_label.pack(anchor="w", pady=(6, 0))

        self.zone_var = tk.StringVar(value=self._zone_text())
        ttk.Label(pad, textvariable=self.zone_var, font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 12))

        btn_row = ttk.Frame(pad)
        btn_row.pack(anchor="w")
        self.pause_btn = ttk.Button(btn_row, text="⏸  Pause", command=self._toggle_pause, width=12)
        self.pause_btn.pack(side="left", padx=(0, 8))
        ttk.Button(btn_row, text="⏹  Close Tracking", command=self.close, width=16).pack(side="left")

        ttk.Separator(pad, orient="horizontal").pack(fill="x", pady=(14, 8))
        hint = ("Tip: q / Esc in the webcam window also closes tracking."
                if self.show_preview else
                "Camera preview window is hidden - use the buttons above to control tracking.")
        ttk.Label(pad, text=hint, font=("Segoe UI", 8), foreground="#777777",
                  wraplength=260, justify="left").pack(anchor="w")

    def _zone_text(self):
        icon = ZONE_ICONS.get(self.confirmed_zone, "")
        return f"Zone: {icon}  {_display_zone(self.confirmed_zone)}"

    def _toggle_pause(self):
        self.paused = not self.paused
        if self.paused:
            self.status_var.set("⏸  Paused")
            self.status_label.configure(foreground=PAUSED_COLOR)
            self.pause_btn.configure(text="▶  Resume")
        else:
            self.status_var.set("●  Tracking")
            self.status_label.configure(foreground=TRACKING_COLOR)
            self.pause_btn.configure(text="⏸  Pause")

    def _step(self):
        if self._closing:
            return

        pose = self.stream.read()
        if pose is None:
            self.close()
            return

        if self.focus_mgr is not None:
            self.focus_mgr.poll()

        frame = pose.frame
        h, w = frame.shape[:2]

        if self.paused:
            if self.show_preview:
                cv2.putText(frame, "PAUSED", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 165, 255), 2)
        elif pose.found:
            new_candidate = zone_classifier.classify_zone(
                pose.yaw, pose.pitch, self.confirmed_zone, self.rules, self.fallback_zone
            )
            if new_candidate != self.candidate_zone:
                self.candidate_zone = new_candidate
                self.candidate_since = time.time()

            if self.candidate_zone != self.confirmed_zone and self.candidate_since is not None:
                if time.time() - self.candidate_since >= DWELL_SECONDS:
                    self.confirmed_zone = self.candidate_zone
                    if self.focus_mgr is not None:
                        self.focus_mgr.switch_to(self.confirmed_zone)
                    self.zone_var.set(self._zone_text())

            if self.show_preview:
                if pose.face_landmarks:
                    for lm in pose.face_landmarks:
                        cv2.circle(frame, (int(lm.x * w), int(lm.y * h)), 1, (0, 255, 0), -1)

                cv2.putText(frame, f"raw yaw: {pose.raw_yaw:6.1f}  pitch: {pose.raw_pitch:6.1f}",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                cv2.putText(frame, f"smoothed yaw: {pose.yaw:6.1f}  pitch: {pose.pitch:6.1f}",
                            (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                cv2.putText(frame, f"candidate: {_display_zone(self.candidate_zone)}",
                            (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
                cv2.putText(frame, f"CONFIRMED: {_display_zone(self.confirmed_zone)}",
                            (10, 130), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
        else:
            if self.show_preview:
                cv2.putText(frame, "NO FACE DETECTED", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

        if self.show_preview:
            cv2.imshow(PREVIEW_WINDOW_TITLE, frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q") or key == 27:
                self.close()
                return

        self.after(10, self._step)

    def close(self):
        if self._closing:
            return
        self._closing = True
        self.stream.close()
        cv2.destroyAllWindows()
        self.destroy()


def main(cfg):
    panel = TrackerControlPanel(cfg)
    panel.mainloop()


if __name__ == "__main__":
    cfg = calibration_ui.run()
    main(cfg)
