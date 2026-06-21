#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path


FINISHED_RE = re.compile(
    r"finished return_code=(?P<return_code>-?\d+) "
    r"elapsed=(?P<elapsed>[0-9.]+)s "
    r"max_speed=(?P<max_speed>[0-9.]+) "
    r"collisions=(?P<collisions>\d+) "
    r"penalties=(?P<penalties>\d+)"
)
MAP_RE = re.compile(r"\[DrivingController\] Map : (?P<map>\d+)")
PROGRESS_RE = re.compile(r"\[Telemetry\] progress=(?P<progress>[0-9.]+)")


def parse_log(path):
    text = Path(path).read_text(errors="replace")
    map_num = None
    max_progress = 0.0
    finished = None

    for line in text.splitlines():
        map_match = MAP_RE.search(line)
        if map_match:
            map_num = map_match.group("map")

        progress_match = PROGRESS_RE.search(line)
        if progress_match:
            max_progress = max(max_progress, float(progress_match.group("progress")))

        finished_match = FINISHED_RE.search(line)
        if finished_match:
            finished = {
                "return_code": int(finished_match.group("return_code")),
                "elapsed": float(finished_match.group("elapsed")),
                "max_speed": float(finished_match.group("max_speed")),
                "collisions": int(finished_match.group("collisions")),
                "penalties": int(finished_match.group("penalties")),
            }

    result = {
        "path": str(path),
        "map": map_num,
        "max_progress": max_progress,
        "finished": finished is not None and finished["return_code"] == 0,
    }
    if finished and finished["return_code"] == 0:
        result.update(finished)
        # SSAFY Race public docs in this workspace do not expose a numeric
        # collision/penalty scoring formula. Rank finished runs by elapsed time;
        # keep collisions and penalties as diagnostics, not hidden penalties.
        result["score"] = finished["elapsed"]
    elif finished:
        result.update(finished)
        result["score"] = 999999.0
    else:
        result.update(
            {
                "return_code": None,
                "elapsed": None,
                "max_speed": None,
                "collisions": None,
                "penalties": None,
                "score": 999999.0,
            }
        )
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("logs", nargs="+")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    rows = [parse_log(path) for path in args.logs]
    rows.sort(key=lambda item: (item.get("map") or "", not item["finished"], item["score"]))

    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
        return

    for row in rows:
        print(
            "{path} map={map} finished={finished} elapsed={elapsed} "
            "score={score:.2f} max_speed={max_speed} collisions={collisions} "
            "penalties={penalties} max_progress={max_progress}".format(**row)
        )


if __name__ == "__main__":
    main()
