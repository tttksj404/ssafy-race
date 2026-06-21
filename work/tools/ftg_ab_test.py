import json,os,re,subprocess
from pathlib import Path
ROOT=Path("/Users/tttksj/Desktop/ssafy-race")
seed=json.load(open(ROOT/"work/experiments/map61_autotune/optuna_seed.json"))["env"]
OUT=ROOT/"work/experiments/ftg_ab_test.txt"
def run(ftg,i):
    env={**os.environ,**{k:str(v) for k,v in seed.items()},"SSAFY_MAP61_FTG_ENABLE":str(ftg)}
    p=subprocess.run(["./work/run_experiment.sh","06",f"ftg{ftg}_{i}"],cwd=str(ROOT),
        text=True,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=900)
    m=re.search(r"\[ExperimentLog\] (.+)",p.stdout); log=m.group(1).strip() if m else ""
    if not log or not Path(log).exists(): return None
    s=subprocess.run(["python3","work/tools/score_logs.py","--json",log],cwd=str(ROOT),text=True,stdout=subprocess.PIPE)
    return json.loads(s.stdout)[0]
open(OUT,"w").write("FTG run fin elapsed col\n")
for ftg in [0,1]:
    for i in [1,2,3]:
        subprocess.run(["pkill","-f","my_car.py"],stderr=subprocess.DEVNULL)
        subprocess.run(["pkill","-f","Algo.exe"],stderr=subprocess.DEVNULL)
        r=run(ftg,i)
        line=f"{ftg} {i} {r.get('finished') if r else 'ERR'} {r.get('elapsed') if r else '-'} {r.get('collisions') if r else '-'}"
        open(OUT,"a").write(line+"\n"); print(line)
print("DONE")
