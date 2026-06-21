import os,re,subprocess,json
from pathlib import Path
ROOT=Path("/Users/tttksj/Desktop/ssafy-race")
MAPS=[("00","map10"),("05","map31"),("06","map61"),("07","map71"),("03","map161")]
MODES=["orig","corridor","visgraph","ensemble"]
OUT=ROOT/"work/experiments/mode_screen.txt"; open(OUT,"w").write("mode map fin elapsed col\n")
def run(idx,mode,name):
    e={**os.environ,"SSAFY_GENERAL_ONLY":"1","SSAFY_AVOID_MODE":mode}
    p=subprocess.run(["./work/run_experiment.sh",idx,f"ms_{mode}_{name}"],cwd=str(ROOT),text=True,env=e,
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=900)
    m=re.search(r"\[ExperimentLog\] (.+)",p.stdout);log=m.group(1).strip() if m else ""
    if not log or not Path(log).exists(): return None
    s=subprocess.run(["python3","work/tools/score_logs.py","--json",log],cwd=str(ROOT),text=True,stdout=subprocess.PIPE)
    return json.loads(s.stdout)[0]
summary={}
for mode in MODES:
    tot=0.0; fins=0
    for idx,name in MAPS:
        subprocess.run(["pkill","-f","my_car.py"],stderr=subprocess.DEVNULL);subprocess.run(["pkill","-f","Algo.exe"],stderr=subprocess.DEVNULL)
        r=run(idx,mode,name)
        fin=r.get('finished') if r else False; el=r.get('elapsed') if r else None
        line=f"{mode} {name} {fin} {el} {r.get('collisions') if r else '-'}"
        open(OUT,"a").write(line+"\n");print(line)
        if fin and el: tot+=el; fins+=1
    summary[mode]=(fins,round(tot,1))
    open(OUT,"a").write(f"# {mode}: 완주 {fins}/5, 총시간 {tot:.1f}\n")
    print(f"# {mode}: 완주 {fins}/5, 총시간 {tot:.1f}")
print("SUMMARY",summary);print("DONE")
