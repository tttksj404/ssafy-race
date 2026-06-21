import json,os,re,subprocess
from pathlib import Path
ROOT=Path("/Users/tttksj/Desktop/ssafy-race")
# R1 챔피언(257.55) env
env0=json.load(open(ROOT/"work/experiments/map61_autotune/champion_orig_r1.json"))["env"]
OUT=ROOT/"work/experiments/stab_ab.txt"; open(OUT,"w").write("STAB run fin elapsed col\n")
def run(stab,i):
    e={**os.environ,**{k:str(v) for k,v in env0.items()},
       "SSAFY_MAP61_AVOID_MODE":"orig","SSAFY_MAP61_STAB_ENABLE":str(stab)}
    p=subprocess.run(["./work/run_experiment.sh","06",f"stab{stab}_{i}"],cwd=str(ROOT),text=True,
        env=e,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=900)
    m=re.search(r"\[ExperimentLog\] (.+)",p.stdout);log=m.group(1).strip() if m else ""
    if not log or not Path(log).exists(): return None
    s=subprocess.run(["python3","work/tools/score_logs.py","--json",log],cwd=str(ROOT),text=True,stdout=subprocess.PIPE)
    return json.loads(s.stdout)[0]
for stab in [0,1]:
    for i in [1,2]:
        subprocess.run(["pkill","-f","my_car.py"],stderr=subprocess.DEVNULL);subprocess.run(["pkill","-f","Algo.exe"],stderr=subprocess.DEVNULL)
        r=run(stab,i)
        line=f"{stab} {i} {r.get('finished') if r else 'ERR'} {r.get('elapsed') if r else '-'} {r.get('collisions') if r else '-'}"
        open(OUT,"a").write(line+"\n");print(line)
print("DONE")
