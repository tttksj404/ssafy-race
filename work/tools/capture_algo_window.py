#!/usr/bin/env python3
import argparse
import os
import subprocess
import time

import Quartz


def find_algo_window():
    options = Quartz.kCGWindowListOptionOnScreenOnly
    windows = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID)
    for win in windows:
        owner = str(win.get("kCGWindowOwnerName", ""))
        title = str(win.get("kCGWindowName", ""))
        if "Algo-Win64-Shipping.exe" in owner or "Algo" in owner or "Algo" in title:
            wid = int(win.get("kCGWindowNumber"))
            bounds = win.get("kCGWindowBounds", {})
            width = int(bounds.get("Width", 0))
            height = int(bounds.get("Height", 0))
            if width > 200 and height > 200:
                return wid, owner, title, width, height
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out_dir")
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--fps", type=float, default=4.0)
    parser.add_argument("--wait", type=float, default=20.0)
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    deadline = time.time() + args.wait
    found = None
    while time.time() < deadline:
        found = find_algo_window()
        if found:
            break
        time.sleep(0.25)
    if not found:
        raise SystemExit("Algo window not found")

    window_id, owner, title, width, height = found
    with open(os.path.join(args.out_dir, "window.txt"), "w", encoding="utf-8") as fp:
        fp.write(f"id={window_id}\nowner={owner}\ntitle={title}\nwidth={width}\nheight={height}\n")

    interval = 1.0 / max(args.fps, 0.1)
    end_at = time.time() + args.duration
    frame = 0
    while time.time() < end_at:
        path = os.path.join(args.out_dir, f"frame_{frame:05d}.jpg")
        subprocess.run(
            ["screencapture", "-x", "-t", "jpg", "-l", str(window_id), path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        frame += 1
        sleep_for = interval - (time.time() % interval)
        time.sleep(max(0.02, min(interval, sleep_for)))


if __name__ == "__main__":
    main()
