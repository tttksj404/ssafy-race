#!/usr/bin/env python3
"""Reusable 2-arm A/B over GENERAL_ONLY 5-map suite. Each arm = a dict of env
overrides on top of the common GENERAL_ONLY+profiler base. Parses elapsed +
collisions + penalties from the telemetry 'finished' line. Flicker-resilient.

Usage:
  ab_knobs.py --tag rank1 --n 1 \
    --base '{"SSAFY_RECOVERY_PROGRESS_GATE":"0.5","SSAFY_GEN_EMERGENCY_ESCAPE_ENABLE":"0"}' \
    --treat '{"SSAFY_RECOVERY_PROGRESS_GATE":"0.0","SSAFY_GEN_EMERGENCY_ESCAPE_ENABLE":"1"}'
"""
import os, re, json, time, argparse, subprocess
from pathlib import Path

ROOT = Path("/Users/tttksj/Desktop/ssafy-race")
RUNNER = ROOT / "work" / "run_experiment.sh"
OUT = ROOT / "work" / "experiments"
MAPS = [("00", "map10"), ("05", "map31"), ("06", "map61"), ("07", "map71"), ("03", "map161")]
COMMON = {"SSAFY_GENERAL_ONLY": "1", "SSAFY_AVOID_MODE": "orig",
          "SSAFY_GEN_SPEED_PROFILE": "1", "SSAFY_GEN_GRIP": "13", "SSAFY_GEN_DECEL": "8",
          "SSAFY_GEN_VMIN": "70"}
FIN = re.compile(r"finished return_code=(\d+) elapsed=([\d.]+)s max_speed=([\d.]+) collisions=(\d+) penalties=(\d+)")


def one_run(arm_env, idx, tag):
    penv = {**os.environ, **COMMON, **arm_env}
    for attempt in range(4):
        try:
            p = subprocess.run([str(RUNNER), idx, f"ab_{tag}"], cwd=str(ROOT), text=True,
                               env=penv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900)
            out = p.stdout
        except subprocess.TimeoutExpired as e:
            out = e.stdout if isinstance(getattr(e, "stdout", None), str) else ""
        m = re.search(r"\[ExperimentLog\] (.+)", out or "")
        log = m.group(1).strip() if m else ""
        txt = ""
        if log and Path(log).exists():
            txt = Path(log).read_text(errors="replace")
        fm = FIN.search(txt)
        if not fm:  # flicker or DNF-no-line: retry
            subprocess.run(["pkill", "-f", "my_car.py"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            subprocess.run(["pkill", "-f", "Algo.exe"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            if attempt < 3:
                time.sleep(18); continue
            return {"rc": None, "elapsed": None, "col": None, "pen": None}
        rc = int(fm.group(1))
        return {"rc": rc, "elapsed": float(fm.group(2)) if rc == 0 else None,
                "col": int(fm.group(4)), "pen": int(fm.group(5)),
                "prog": _last_prog(txt)}


def _last_prog(txt):
    pr = re.findall(r"progress=([\d.]+)", txt)
    return float(pr[-1]) if pr else 0.0


def run_arm(name, arm_env, n, tag):
    rows = {}
    for idx, mp in MAPS:
        runs = [one_run(arm_env, idx, f"{tag}_{name}_{mp}") for _ in range(n)]
        fins = [r for r in runs if r["rc"] == 0]
        if fins:
            best = min(fins, key=lambda r: r["elapsed"])
            rows[mp] = {"elapsed": round(best["elapsed"], 1), "col": best["col"], "pen": best["pen"],
                        "fin": len(fins), "n": n}
        else:
            r = runs[-1]
            rows[mp] = {"elapsed": None, "col": r["col"], "pen": r["pen"], "fin": 0, "n": n,
                        "prog": r.get("prog")}
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--base", required=True)
    ap.add_argument("--treat", required=True)
    a = ap.parse_args()
    base_env, treat_env = json.loads(a.base), json.loads(a.treat)
    outf = OUT / f"ab_{a.tag}.txt"

    res = {}
    for nm, env in [("BASE", base_env), ("TREAT", treat_env)]:
        res[nm] = run_arm(nm, env, a.n, a.tag)
        lines = [f"=== {a.tag} {nm} env={json.dumps(env)} ==="]
        tot, allfin = 0.0, True
        for _, mp in MAPS:
            r = res[nm][mp]
            if r["elapsed"] is not None:
                tot += r["elapsed"]
                lines.append(f"{mp} {r['elapsed']}s col={r['col']} pen={r['pen']} ({r['fin']}/{r['n']})")
            else:
                allfin = False
                lines.append(f"{mp} DNF prog={r.get('prog')} col={r['col']} pen={r['pen']}")
        lines.append(f"# {nm} TOTAL={'%.1f' % tot if allfin else 'DNF(>=1)'} (allfin={allfin})\n")
        with open(outf, "a") as f:
            f.write("\n".join(lines) + "\n")
        print("\n".join(lines))
    with open(outf, "a") as f:
        f.write(f"updated={time.strftime('%F %T')}\nDONE\n")
    print("DONE")


if __name__ == "__main__":
    raise SystemExit(main())
