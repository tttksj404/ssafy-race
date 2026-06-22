#!/usr/bin/env python3
"""Multi-map GENERAL-algorithm tuner. Tunes the map-AGNOSTIC knobs (general
recovery + general obstacle clearance) of the winning 'orig' avoidance, evaluated
with SSAFY_GENERAL_ONLY=1 (all map-specific hardcoding disabled) across ALL 5
known maps as a proxy for UNSEEN test maps. Objective: every map must finish;
minimize total elapsed (a DNF dominates). Optuna TPE, resumable, flicker-resilient.
"""
import os, re, json, time, argparse, subprocess, optuna
from pathlib import Path

ROOT = Path("/Users/tttksj/Desktop/ssafy-race")
RUNNER = ROOT / "work" / "run_experiment.sh"
SCORER = ROOT / "work" / "tools" / "score_logs.py"
OUT = ROOT / "work" / "experiments" / "general_tune"
OUT.mkdir(parents=True, exist_ok=True)
MAPS = [("00", "map10"), ("05", "map31"), ("06", "map61"), ("07", "map71"), ("03", "map161")]

KNOBS = {
    "SSAFY_RECOVERY_TRIGGER":        ("int",   [3, 4, 5, 6, 8]),
    "SSAFY_RECOVERY_BACK_STEER":     ("float", [0.35, 0.45, 0.55, 0.65]),
    "SSAFY_RECOVERY_BACK_THROTTLE":  ("float", [0.6, 0.75, 0.9, 1.0]),
    "SSAFY_RECOVERY_BACK_FRAMES":    ("int",   [6, 8, 10, 12, 14]),
    "SSAFY_RECOVERY_FORWARD_STEER":  ("float", [0.35, 0.45, 0.55, 0.7]),
    "SSAFY_RECOVERY_FORWARD_FRAMES": ("int",   [4, 6, 8, 10, 12]),
    "SSAFY_RECOVERY_DONE_SPEED":     ("float", [12.0, 14.0, 18.0, 22.0]),
    "SSAFY_GEN_OBSTACLE_PED":        ("float", [1.8, 2.25, 2.7, 3.2]),
    "SSAFY_GEN_GRIP":                ("float", [9.0, 11.0, 13.0, 15.0, 18.0]),
    "SSAFY_GEN_DECEL":               ("float", [6.0, 8.0, 10.0, 12.0]),
    "SSAFY_GEN_VMIN":                ("float", [60.0, 70.0, 80.0]),
}
SEED = {"SSAFY_RECOVERY_TRIGGER": 8, "SSAFY_RECOVERY_BACK_STEER": 0.45,
        "SSAFY_RECOVERY_BACK_THROTTLE": 0.75, "SSAFY_RECOVERY_BACK_FRAMES": 8,
        "SSAFY_RECOVERY_FORWARD_STEER": 0.55, "SSAFY_RECOVERY_FORWARD_FRAMES": 12,
        "SSAFY_RECOVERY_DONE_SPEED": 18.0, "SSAFY_GEN_OBSTACLE_PED": 2.25,
        "SSAFY_GEN_GRIP": 13.0, "SSAFY_GEN_DECEL": 8.0, "SSAFY_GEN_VMIN": 70.0}


def fmt(env):
    out = {}
    for k, v in env.items():
        out[k] = str(int(v)) if KNOBS[k][0] == "int" else f"{float(v):g}"
    return out


def score_run(env, tag):
    """One GENERAL_ONLY run on one map. Retries flicker crashes; real DNF kept."""
    penv = {**os.environ, **fmt(env), "SSAFY_GENERAL_ONLY": "1", "SSAFY_AVOID_MODE": "orig", "SSAFY_GEN_SPEED_PROFILE": "1"}
    for attempt in range(4):
        try:
            p = subprocess.run([str(RUNNER), tag.split("|")[0], f"gt_{tag.split('|')[1]}"],
                               cwd=str(ROOT), text=True, env=penv,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900)
            out = p.stdout
        except subprocess.TimeoutExpired as e:
            out = e.stdout if isinstance(getattr(e, "stdout", None), str) else ""
        m = re.search(r"\[ExperimentLog\] (.+)", out or "")
        log = m.group(1).strip() if m else ""
        flicker = (det := (not log or not Path(log).exists()))
        if not flicker:
            try:
                if "finished return_code" not in Path(log).read_text(errors="replace"):
                    flicker = True
            except Exception:
                flicker = True
        if flicker:
            subprocess.run(["pkill", "-f", "my_car.py"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            subprocess.run(["pkill", "-f", "Algo.exe"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            if attempt < 3:
                time.sleep(20); continue
            return {"finished": False, "elapsed": None, "max_progress": 0.0, "error": "flicker"}
        s = subprocess.run(["python3", str(SCORER), "--json", log], cwd=str(ROOT),
                           text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            return json.loads(s.stdout)[0]
        except Exception:
            return {"finished": False, "max_progress": 0.0, "error": "parse"}


def evaluate(env, tag):
    total, fins, per = 0.0, 0, {}
    for idx, name in MAPS:
        subprocess.run(["pkill", "-f", "my_car.py"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        subprocess.run(["pkill", "-f", "Algo.exe"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        r = score_run(env, f"{idx}|{tag}_{name}")
        if r.get("finished"):
            fins += 1; total += r.get("elapsed") or 0.0
            per[name] = round(r.get("elapsed") or 0, 1)
        else:
            total += 100000.0 - (r.get("max_progress") or 0.0) * 100.0  # DNF dominates
            per[name] = "DNF"
    return {"score": round(total, 1), "finishes": fins, "n": len(MAPS), "per": per}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--patience", type=int, default=20)
    ap.add_argument("--trials", type=int, default=300)
    ap.add_argument("--seed", type=int, default=20260621)
    a = ap.parse_args()
    study = optuna.create_study(
        sampler=optuna.samplers.TPESampler(seed=a.seed, n_startup_trials=6, multivariate=True),
        direction="minimize", storage="sqlite:///" + str(OUT / "optuna.db"),
        study_name="general", load_if_exists=True)
    if len(study.trials) == 0:
        study.enqueue_trial(SEED)
    st = {"best": float("inf"), "bt": -1, "be": None, "br": None}

    def cb(study, trial):
        if trial.state.name != "COMPLETE":
            return
        r = trial.user_attrs.get("r")
        if r is None:
            return
        v = trial.values[0]
        if v < st["best"]:
            st.update(best=v, bt=trial.number, be=dict(trial.params), br=r)
            (OUT / "champion.json").write_text(json.dumps({"env": fmt(st["be"]), "result": st["br"]}, indent=2, sort_keys=True))
        (OUT / "STATUS.txt").write_text(
            f"trials={len(study.trials)} best={st['best']:.1f} finishes={st['br']['finishes']}/{st['br']['n']} "
            f"no_improve={trial.number - st['bt']}\nbest_per={json.dumps(st['br']['per'])}\n"
            f"best_env={json.dumps(fmt(st['be']))}\nlast={v:.1f} {json.dumps(r['per'])}\nupdated={time.strftime('%F %T')}\n")
        print("[t%d] total=%.1f fin=%d/%d %s" % (trial.number, v, r["finishes"], r["n"], json.dumps(r["per"])))
        if trial.number - st["bt"] >= a.patience:
            study.stop()

    def obj(trial):
        env = {n: trial.suggest_categorical(n, ch) for n, (_, ch) in KNOBS.items()}
        r = evaluate(env, f"t{trial.number:03d}")
        trial.set_user_attr("r", r)
        return r["score"]

    study.optimize(obj, n_trials=a.trials, callbacks=[cb])
    print("[done] best=%.1f env=%s" % (st["best"], json.dumps(fmt(st["be"] or {}))))


if __name__ == "__main__":
    raise SystemExit(main())
