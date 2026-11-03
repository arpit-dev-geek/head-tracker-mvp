"""
Loads/saves the user's calibrated head-tracker settings as JSON, so the
tkinter setup UI and the tracker itself share one on-disk source of truth
instead of hardcoded constants in head_tracker_mvp.py.
"""

import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tracker_config.json")

DEFAULTS = {
    "layout": "3",                 # "3" | "2_side" | "2_vertical"
    "yaw_left_enter": -15.0,
    "yaw_left_exit": -10.0,
    "yaw_right_enter": 10.0,
    "yaw_right_exit": 5.0,
    "pitch_down_enter": -15.0,      # LAPTOP, used by "3" and "2_side"
    "pitch_down_exit": -10.0,
    "pitch_top_enter": 15.0,        # TOP, used by "2_vertical"
    "pitch_top_exit": 10.0,
    "side_zone": "LEFT",            # "LEFT" | "RIGHT" - which side the single external monitor is on, for "2_side"
    "yaw_sign": 1,
    "pitch_sign": 1,
    "show_preview": True,           # whether to show the live webcam preview window while tracking
}


def load():
    """Returns DEFAULTS merged with tracker_config.json's contents, if present."""
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    return cfg


def save(cfg):
    """Writes cfg (merged over DEFAULTS, so partial updates are safe) to disk."""
    merged = dict(DEFAULTS)
    merged.update(cfg)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2)
    return merged
