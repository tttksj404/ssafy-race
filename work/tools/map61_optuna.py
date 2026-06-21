#!/usr/bin/env python3
"""Optuna(TPE) Bayesian optimization driver for the map61 tuner.

Search-driver only: REUSES the verified eval machinery (3-run-mean sim
execution) from map61_autotune. TPE is sample-efficient for this
expensive+noisy+multi-dim blackbox; resumable via SQLite storage.

Seeds the search from `optuna_seed.json` (the hill-climb champion) + the static
SEED so it starts from known-good points instead of cold.
"""
import os
import sys
import json
import time
import argparse
import optuna

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from map61_autotune import KNOBS, SEED, evaluate, fmt, OUT_DIR, CHAMPION, STATUS

SEED_FILE = OUT_DIR / "optuna_seed.json"


def typed(env):
    """Convert a (possibly stringified) env to typed values matching KNOBS choices."""
    out = {}
    for name, value in env.items():
        if name not in KNOBS:
            continue
        kind, choices = KNOBS[name]
        if kind == "bool":
            v = str(value)
            if v not in choices:
                v = "1" if str(value).strip().lower() not in {"0", "false", "no", "off"} else "0"
            out[name] = v
            continue
        if kind == "cat":
            v = str(value)
            out[name] = v if v in choices else choices[0]
            continue
        v = int(float(value)) if kind == "int" else float(value)
        # snap to the nearest valid choice so suggest_categorical accepts it
        if v not in choices:
            v = min(choices, key=lambda c: abs(c - v))
        out[name] = v
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--patience", type=int, default=15)
    parser.add_argument("--trials", type=int, default=80)
    parser.add_argument("--seed", type=int, default=20260617)
    parser.add_argument("--mode", default="")  # fix AVOID_MODE => per-mode EXTREME tuning
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    sfx = f"_{args.mode}" if args.mode else ""
    champ_path = OUT_DIR / f"champion{sfx}.json"
    status_path = OUT_DIR / f"STATUS{sfx}.txt"
    sampler = optuna.samplers.TPESampler(
        seed=args.seed, n_startup_trials=8, multivariate=True)
    study = optuna.create_study(
        sampler=sampler, direction="minimize",
        storage="sqlite:///" + str(OUT_DIR / f"optuna{sfx}.db"),
        study_name=f"map61{sfx}", load_if_exists=True)

    # Seed from known-good points only on a fresh study (resume already has them).
    def _with_mode(d):
        d = dict(d)
        if args.mode:
            d["SSAFY_MAP61_AVOID_MODE"] = args.mode
        return d

    if len(study.trials) == 0:
        study.enqueue_trial(_with_mode(typed(SEED)))
        if SEED_FILE.exists():
            try:
                env = json.loads(SEED_FILE.read_text()).get("env", {})
                seeded = typed(env)
                if seeded:
                    study.enqueue_trial(_with_mode(seeded))
                    print(f"[seed] enqueued champion (mode={args.mode or 'search'})")
                    if args.mode and "SSAFY_MAP61_STAB_ENABLE" in KNOBS:
                        sv = _with_mode(dict(seeded))
                        sv["SSAFY_MAP61_STAB_ENABLE"] = "1"
                        study.enqueue_trial(sv)
                        print("[seed] enqueued STAB-on variant")
                    if not args.mode:
                        _modes = KNOBS.get("SSAFY_MAP61_AVOID_MODE", (None, []))[1]
                        for _m in ("corridor", "kinematic", "arc", "visgraph", "ensemble"):
                            if _m in _modes:
                                cv = dict(seeded)
                                cv["SSAFY_MAP61_AVOID_MODE"] = _m
                                study.enqueue_trial(cv)
                                print(f"[seed] enqueued {_m}-mode variant")
            except Exception as exc:
                print(f"[seed] skip champion seed: {exc}")

    state = {"best": float("inf"), "best_trial": -1, "best_env": None, "best_r": None}

    def callback(study, trial):
        if trial.state != optuna.trial.TrialState.COMPLETE:
            return
        r = trial.user_attrs.get("r")
        if r is None:
            return
        score = trial.values[0]
        improved = score < state["best"]
        if improved:
            state.update(best=score, best_trial=trial.number,
                         best_env=_with_mode(dict(trial.params)), best_r=r)
            champ_path.write_text(json.dumps(
                {"env": fmt(state["best_env"]), "result": state["best_r"]},
                indent=2, sort_keys=True))
        status_path.write_text(
            f"trials={len(study.trials)} best_score={state['best']:.3f} "
            f"finishes={state['best_r']['finishes']}/{state['best_r']['n']} "
            f"worst={state['best_r']['worst']:.3f} "
            f"no_improve={trial.number - state['best_trial']}\n"
            f"best_env={json.dumps(fmt(state['best_env']))}\n"
            f"last_trial score={score:.3f} finishes={r['finishes']}/{r['n']}\n"
            f"updated={time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        print("[t%d] score=%.3f fin=%d/%d worst=%.3f %s" % (
            trial.number, score, r["finishes"], r["n"], r["worst"],
            "*BEST*" if improved else "(best=%.3f ni=%d)" % (
                state["best"], trial.number - state["best_trial"])))
        if trial.number - state["best_trial"] >= args.patience:
            print(f"[stop] patience {args.patience} reached")
            study.stop()

    def objective(trial):
        env = {}
        for name, (_, choices) in KNOBS.items():
            if name == "SSAFY_MAP61_AVOID_MODE" and args.mode:
                env[name] = args.mode  # fixed => tune THIS algorithm to its extreme
            else:
                env[name] = trial.suggest_categorical(name, choices)
        r = evaluate(env, f"opt{args.mode or 'j'}{trial.number:03d}")
        trial.set_user_attr("r", r)
        return r["score"]

    study.optimize(objective, n_trials=args.trials, callbacks=[callback])
    print("[done] trials=%d BEST score=%.3f env=%s" % (
        len(study.trials), state["best"], json.dumps(fmt(state["best_env"] or {}))))


if __name__ == "__main__":
    main()
