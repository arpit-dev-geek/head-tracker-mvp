"""
Auto-detect-settle calibration wizard: for each zone the current layout
needs, shows a cv2 window instructing the user to hold a head position; once
the measured angle stops moving for a short window, it's captured
automatically (no key press needed).
"""

import time
from collections import deque

import cv2

import head_pose
import zone_classifier

EPSILON_DEGREES = 2.5     # max spread within the rolling window to count as "settled"
SETTLE_SECONDS = 1.2      # how long it must stay settled before capturing
HISTORY_SIZE = 15
MARGIN_FACTOR = 0.8       # captured threshold is 80% of the held angle, so you
                          # don't have to turn all the way to the calibrated edge every time

INSTRUCTIONS = {
    "LEFT": "Turn LEFT toward that monitor and hold still",
    "RIGHT": "Turn RIGHT toward that monitor and hold still",
    "LAPTOP": "Tilt DOWN toward the laptop screen and hold still",
    "TOP": "Look UP toward the top monitor and hold still",
}

WINDOW_NAME = "Calibration (hold still - ESC to cancel)"


def _settle_capture(stream, rule):
    axis = rule["axis"]
    direction = rule["dir"]
    instruction = INSTRUCTIONS.get(rule["zone"], "Hold still")
    history = deque(maxlen=HISTORY_SIZE)
    settle_start = None

    while True:
        pose = stream.read()
        if pose is None:
            return None  # camera died
        frame = pose.frame
        value = pose.yaw if axis == "yaw" else pose.pitch

        cv2.putText(frame, instruction, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        if value is not None:
            cv2.putText(frame, f"{axis}: {value:6.1f}", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)
        else:
            cv2.putText(frame, "NO FACE DETECTED", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        cv2.imshow(WINDOW_NAME, frame)

        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            return None  # user cancelled

        if value is None:
            history.clear()
            settle_start = None
            continue

        history.append(value)
        if len(history) < history.maxlen:
            settle_start = None
            continue

        if max(history) - min(history) > EPSILON_DEGREES:
            settle_start = None
            continue

        if settle_start is None:
            settle_start = time.time()
            continue

        if time.time() - settle_start < SETTLE_SECONDS:
            continue

        mean = sum(history) / len(history)
        expected_negative = direction == "low"
        if mean == 0 or (mean < 0) != expected_negative:
            # Settled, but on the wrong side of zero for this zone - probably
            # means the head drifted back to neutral. Keep waiting.
            settle_start = None
            continue

        return float(mean)


def run(cfg, model_path="face_landmarker.task"):
    """Walks through every zone cfg["layout"] needs, auto-capturing each
    one's threshold angle. Returns {zone: enter_angle} (margin already
    applied), or None if the user cancelled (ESC)."""
    rules, _fallback_zone = zone_classifier.build_rules(cfg)

    stream = head_pose.HeadPoseStream(
        model_path, yaw_sign=cfg["yaw_sign"], pitch_sign=cfg["pitch_sign"]
    )
    captured = {}
    try:
        for rule in rules:
            value = _settle_capture(stream, rule)
            if value is None:
                return None
            captured[rule["zone"]] = value * MARGIN_FACTOR
    finally:
        stream.close()
        try:
            cv2.destroyWindow(WINDOW_NAME)
        except cv2.error:
            pass

    return captured
