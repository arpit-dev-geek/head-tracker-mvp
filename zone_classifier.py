"""
Generalized rule-based zone classifier.

A "rule" is {"zone": str, "axis": "yaw"|"pitch", "dir": "low"|"high",
"enter": float, "exit": float}. dir="low" means the zone is entered once
the value drops to/below `enter`, and holds (hysteresis) until the value
rises back above `exit`. dir="high" mirrors that for crossing upward.

There is no neutral/CENTER zone in any layout: if nothing's entry
threshold is crossed and the current zone has released (hysteresis exit
crossed), classification falls back to `fallback_zone`.
"""


def classify_zone(yaw, pitch, current_zone, rules, fallback_zone):
    values = {"yaw": yaw, "pitch": pitch}

    for rule in rules:
        v = values[rule["axis"]]
        entered = v <= rule["enter"] if rule["dir"] == "low" else v >= rule["enter"]
        if entered:
            return rule["zone"]

    for rule in rules:
        if rule["zone"] == current_zone:
            v = values[rule["axis"]]
            stays = v <= rule["exit"] if rule["dir"] == "low" else v >= rule["exit"]
            if stays:
                return current_zone

    return fallback_zone


def build_rules(cfg):
    """Returns (rules, fallback_zone) for cfg["layout"] ("3" | "2_side" | "2_vertical")."""
    layout = cfg["layout"]

    if layout == "3":
        rules = [
            {"zone": "LEFT", "axis": "yaw", "dir": "low",
             "enter": cfg["yaw_left_enter"], "exit": cfg["yaw_left_exit"]},
            {"zone": "RIGHT", "axis": "yaw", "dir": "high",
             "enter": cfg["yaw_right_enter"], "exit": cfg["yaw_right_exit"]},
            {"zone": "LAPTOP", "axis": "pitch", "dir": "low",
             "enter": cfg["pitch_down_enter"], "exit": cfg["pitch_down_exit"]},
        ]
        return rules, "LAPTOP"

    if layout == "2_side":
        side = cfg["side_zone"]
        side_rule = (
            {"zone": "LEFT", "axis": "yaw", "dir": "low",
             "enter": cfg["yaw_left_enter"], "exit": cfg["yaw_left_exit"]}
            if side == "LEFT" else
            {"zone": "RIGHT", "axis": "yaw", "dir": "high",
             "enter": cfg["yaw_right_enter"], "exit": cfg["yaw_right_exit"]}
        )
        rules = [
            side_rule,
            {"zone": "LAPTOP", "axis": "pitch", "dir": "low",
             "enter": cfg["pitch_down_enter"], "exit": cfg["pitch_down_exit"]},
        ]
        return rules, "LAPTOP"

    if layout == "2_vertical":
        rules = [
            {"zone": "TOP", "axis": "pitch", "dir": "high",
             "enter": cfg["pitch_top_enter"], "exit": cfg["pitch_top_exit"]},
        ]
        return rules, "LAPTOP"

    raise RuntimeError(f"Unknown layout: {layout!r} (expected '3', '2_side', or '2_vertical')")
