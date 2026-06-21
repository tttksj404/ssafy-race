import os,re,subprocess,json
from pathlib import Path
ROOT=Path("/Users/tttksj/Desktop/ssafy-race")
OUT=ROOT/"work/experiments/guard_verify.txt"; open(OUT,"w").write("case fin elapsed col\n")
def run(idx,tag,gen):
    e={**os.environ}; 
    if gen: e["SSAFY_GENERAL_ONLY"]="1"
    p=subprocess.run(["./work/run_experiment.sh",idx,f"gv_{tag}"],cwd=str(ROOT),text=True,env=e,
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=900)
    m=re.search(r"\[ExperimentLog\] (.+)",p.stdout);log=m.group(1).strip() if m else ""
    if not log or not Path(log).exists(): return None
    s=subprocess.run(["python3","work/tools/score_logs.py","--json",log],cwd=str(ROOT),text=True,stdout=subprocess.PIPE)
    return json.loads(s.stdout)[0]
cases=[("05","map31_NORMAL",False),("05","map31_GENERAL",True),("03","map161_GENERAL",True)]
for idx,tag,gen in cases:
    subprocess.run(["pkill","-f","my_car.py"],stderr=subprocess.DEVNULL);subprocess.run(["pkill","-f","Algo.exe"],stderr=subprocess.DEVNULL)
    r=run(idx,tag,gen)
    line=f"{tag} {r.get('finished') if r else 'ERR'} {r.get('elapsed') if r else '-'} {r.get('collisions') if r else '-'}"
    open(OUT,"a").write(line+"\n");print(line)
print("DONE")
