"""
Windows-only window-focus switching, driven by head-tracker zone changes.

Maps the three logical zones (LEFT / RIGHT / LAPTOP) to real Windows
monitors, remembers whichever window was last focused on each monitor, and
can force Windows focus back to that window when a zone becomes active.

Requires pywin32 (`pip install pywin32`).
"""

import win32api
import win32con
import win32gui
import win32process

ZONES = ("LEFT", "RIGHT", "LAPTOP", "TOP")


def _list_monitors():
    """Returns a list of dicts: {handle, left, top, right, bottom, is_primary}."""
    monitors = []
    for handle, _hdc, _rect in win32api.EnumDisplayMonitors(None, None):
        info = win32api.GetMonitorInfo(handle)
        left, top, right, bottom = info["Monitor"]
        is_primary = bool(info["Flags"] & win32con.MONITORINFOF_PRIMARY)
        monitors.append({
            # Normalize to a plain int: EnumDisplayMonitors and
            # MonitorFromWindow can hand back HMONITOR as different
            # wrapper types that otherwise fail to compare/hash equal.
            "handle": int(handle),
            "left": left,
            "top": top,
            "right": right,
            "bottom": bottom,
            "is_primary": is_primary,
        })
    return monitors


def build_zone_monitor_map(layout):
    """Maps zone names to real monitor handles for the given layout.

    layout="3": laptop screen in the middle, one external monitor each
    side. Leftmost monitor -> LEFT, rightmost -> RIGHT, the remaining
    middle one -> LAPTOP.

    layout="2_side": laptop + one external monitor on either side. The
    primary monitor -> LAPTOP, the other monitor -> LEFT or RIGHT
    depending on which side of the primary it sits.

    layout="2_vertical": laptop + one external monitor stacked above or
    below it. The primary monitor -> LAPTOP, the other -> TOP (regardless
    of whether it's physically above or below - there are only two zones).
    """
    monitors = _list_monitors()

    if layout == "3":
        monitors.sort(key=lambda m: m["left"])
        if len(monitors) != 3:
            raise RuntimeError(
                f"Layout is '3' but {len(monitors)} monitor(s) were "
                "detected. Pick a different layout or fix your monitor setup."
            )
        left_mon, laptop_mon, right_mon = monitors
        return {"LEFT": left_mon["handle"], "LAPTOP": laptop_mon["handle"],
                "RIGHT": right_mon["handle"]}

    if layout == "2_side":
        monitors.sort(key=lambda m: m["left"])
        if len(monitors) != 2:
            raise RuntimeError(
                f"Layout is '2_side' but {len(monitors)} monitor(s) were "
                "detected. Pick a different layout or fix your monitor setup."
            )
        primary = next((m for m in monitors if m["is_primary"]), monitors[0])
        other = next(m for m in monitors if m is not primary)
        other_zone = "LEFT" if other["left"] < primary["left"] else "RIGHT"
        return {"LAPTOP": primary["handle"], other_zone: other["handle"]}

    if layout == "2_vertical":
        if len(monitors) != 2:
            raise RuntimeError(
                f"Layout is '2_vertical' but {len(monitors)} monitor(s) were "
                "detected. Pick a different layout or fix your monitor setup."
            )
        primary = next((m for m in monitors if m["is_primary"]), monitors[0])
        other = next(m for m in monitors if m is not primary)
        return {"LAPTOP": primary["handle"], "TOP": other["handle"]}

    raise RuntimeError(f"Unknown layout: {layout!r} (expected '3', '2_side', or '2_vertical')")


def detect_side_zone():
    """Best-effort detection of which side the single external monitor is
    on, for layout="2_side". Returns "LEFT" or "RIGHT"; defaults to
    "RIGHT" if detection fails (e.g. wrong monitor count plugged in right
    now) so the UI still has something sensible to show."""
    try:
        mapping = build_zone_monitor_map("2_side")
        return next(zone for zone in mapping if zone != "LAPTOP")
    except Exception:
        return "RIGHT"


def _window_title(hwnd):
    try:
        return win32gui.GetWindowText(hwnd) or "(untitled window)"
    except Exception:
        return "(unknown window)"


def force_set_foreground(hwnd):
    """Forces Windows focus onto hwnd, working around the foreground lock."""
    fg_hwnd = win32gui.GetForegroundWindow()
    cur_thread = win32api.GetCurrentThreadId()
    fg_thread, _ = win32process.GetWindowThreadProcessId(fg_hwnd) if fg_hwnd else (0, 0)
    target_thread, _ = win32process.GetWindowThreadProcessId(hwnd)

    attached_fg = attached_target = False
    try:
        if fg_thread and fg_thread != cur_thread:
            win32process.AttachThreadInput(cur_thread, fg_thread, True)
            attached_fg = True
        if target_thread and target_thread != cur_thread:
            win32process.AttachThreadInput(cur_thread, target_thread, True)
            attached_target = True

        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
    finally:
        if attached_fg:
            win32process.AttachThreadInput(cur_thread, fg_thread, False)
        if attached_target:
            win32process.AttachThreadInput(cur_thread, target_thread, False)


class WindowFocusManager:
    """Tracks the last-focused window per zone and can restore it on demand."""

    def __init__(self, zone_monitor_map, own_window_titles):
        self._zone_by_monitor = {
            handle: zone for zone, handle in zone_monitor_map.items()
        }
        self._last_focused = {}
        self._own_window_titles = (
            [own_window_titles] if isinstance(own_window_titles, str) else list(own_window_titles)
        )
        self._own_hwnds = {}

    def _get_own_hwnds(self):
        """The app can own more than one real window at once (e.g. the cv2
        preview and a tkinter control panel) - resolve + cache a handle per
        title, re-resolving only if a cached handle has gone stale."""
        for title in self._own_window_titles:
            hwnd = self._own_hwnds.get(title)
            if hwnd is None or not win32gui.IsWindow(hwnd):
                self._own_hwnds[title] = win32gui.FindWindow(None, title)
        return {hwnd for hwnd in self._own_hwnds.values() if hwnd}

    def seed_from_current_windows(self):
        """Records whichever window is currently on top on each zone's
        monitor, so focus-restore has something to switch to immediately
        on startup instead of waiting for the user to click into each
        monitor once. EnumWindows visits top-level windows in Z-order
        (topmost first), so the first visible, titled window seen per
        monitor is whatever's currently showing there."""
        own_hwnds = self._get_own_hwnds()

        def _visit(hwnd, _extra):
            if (
                hwnd not in own_hwnds
                and win32gui.IsWindowVisible(hwnd)
                and not win32gui.IsIconic(hwnd)
                and win32gui.GetWindowText(hwnd)
            ):
                monitor_handle = int(win32api.MonitorFromWindow(
                    hwnd, win32con.MONITOR_DEFAULTTONEAREST
                ))
                zone = self._zone_by_monitor.get(monitor_handle)
                if zone is not None and zone not in self._last_focused:
                    self._last_focused[zone] = hwnd
            return True

        win32gui.EnumWindows(_visit, None)
        for zone, hwnd in self._last_focused.items():
            print(f"[window_focus] seeded {zone}: {_window_title(hwnd)!r}")

    def poll(self):
        """Call once per frame to keep the last-focused-per-zone map current."""
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd or hwnd in self._get_own_hwnds():
            return

        monitor_handle = int(win32api.MonitorFromWindow(
            hwnd, win32con.MONITOR_DEFAULTTONEAREST
        ))
        zone = self._zone_by_monitor.get(monitor_handle)
        if zone is not None:
            self._last_focused[zone] = hwnd

    def switch_to(self, zone):
        """Forces focus back to the last-focused window recorded for zone."""
        hwnd = self._last_focused.get(zone)
        if hwnd is None:
            print(f"[window_focus] no window recorded for zone {zone} yet")
            return
        if not win32gui.IsWindow(hwnd):
            print(f"[window_focus] window last focused on {zone} no longer exists")
            del self._last_focused[zone]
            return

        print(f"[window_focus] switching to {zone}: {_window_title(hwnd)!r}")
        force_set_foreground(hwnd)
