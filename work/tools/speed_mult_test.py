import json,os,re,subprocess,sys
from pathlib import Path
ROOT=Path("/Users/tttksj/Desktop/ssafy-race")
seed=json.load(open(ROOT/"work/experiments/map61_autotune/optuna_seed.json"))["env"]
OUT=ROOT/"work/experiments/speed_mult_test.txt"
def run(mult,i):
    env={**os.environ,**{k:str(v) for k,v in seed.items()},"SSAFY_MAP61_SPEED_MULT":str(mult)}
    p=subprocess.run(["./work/run_experiment.sh","06",f"smult_{mult}_{i}"],cwd=str(ROOT),
        text=True,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=900)
    m=re.search(r"\[ExperimentLog\] (.+)",p.stdout); log=m.group(1).strip() if m else ""
    if not log or not Path(log).exists(): return None
    s=subprocess.run(["python3","work/tools/score_logs.py","--json",log],cwd=str(ROOT),
        text=True,stdout=subprocess.PIPE); r=json.loads(s.stdout)[0]
    return r
with open(OUT,"w") as f: f.write("mult run fin elapsed col\n")
for mult in [1.0,1.1,1.2]:
    for i in [1,2]:
        subprocess.run(["pkill","-f","my_car.py"],stderr=subprocess.DEVNULL)
        subprocess.run(["pkill","-f","Algo.exe"],stderr=subprocess.DEVNULL)
        r=run(mult,i)
        line=f"{mult} {i} {r.get('finished') if r else 'ERR'} {r.get('elapsed') if r else '-'} {r.get('collisions') if r else '-'}"
        with open(OUT,"a") as f: f.write(line+"\n")
        print(line)
print("DONE")
