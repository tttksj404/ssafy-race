import os,re,subprocess,json
from pathlib import Path
ROOT=Path("/Users/tttksj/Desktop/ssafy-race")
# settings index -> map name
MAPS=[("00","map10"),("05","map31"),("06","map61"),("07","map71"),("03","map161")]
OUT=ROOT/"work/experiments/holdout_pure.txt"; open(OUT,"w").write("map fin elapsed col maxprog\n")
def run(idx,name):
    e={**os.environ,"SSAFY_GENERAL_ONLY":"1"}
    p=subprocess.run(["./work/run_experiment.sh",idx,f"holdoutpure_{name}"],cwd=str(ROOT),text=True,
        env=e,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=900)
    m=re.search(r"\[ExperimentLog\] (.+)",p.stdout);log=m.group(1).strip() if m else ""
    if not log or not Path(log).exists(): return None
    s=subprocess.run(["python3","work/tools/score_logs.py","--json",log],cwd=str(ROOT),text=True,stdout=subprocess.PIPE)
    return json.loads(s.stdout)[0]
for idx,name in MAPS:
    subprocess.run(["pkill","-f","my_car.py"],stderr=subprocess.DEVNULL);subprocess.run(["pkill","-f","Algo.exe"],stderr=subprocess.DEVNULL)
    r=run(idx,name)
    line=f"{name} {r.get('finished') if r else 'ERR'} {r.get('elapsed') if r else '-'} {r.get('collisions') if r else '-'} {r.get('max_progress') if r else '-'}"
    open(OUT,"a").write(line+"\n");print(line)
print("DONE")
