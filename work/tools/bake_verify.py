import os,re,subprocess,json
from pathlib import Path
ROOT=Path("/Users/tttksj/Desktop/ssafy-race")
OUT=ROOT/"work/experiments/bake_verify.txt"; open(OUT,"w").write("case fin elapsed col\n")
def run(idx,tag,gen):
    e={**os.environ}
    if gen: e["SSAFY_GENERAL_ONLY"]="1"; e["SSAFY_AVOID_MODE"]="orig"
    for att in range(3):
        p=subprocess.run(["./work/run_experiment.sh",idx,f"bv_{tag}"],cwd=str(ROOT),text=True,env=e,
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=900)
        m=re.search(r"\[ExperimentLog\] (.+)",p.stdout);log=m.group(1).strip() if m else ""
        if log and Path(log).exists() and "finished return_code" in Path(log).read_text(errors="replace"):
            s=subprocess.run(["python3","work/tools/score_logs.py","--json",log],cwd=str(ROOT),text=True,stdout=subprocess.PIPE)
            return json.loads(s.stdout)[0]
        subprocess.run(["pkill","-f","my_car.py"],stderr=subprocess.DEVNULL);subprocess.run(["pkill","-f","Algo.exe"],stderr=subprocess.DEVNULL);import time;time.sleep(15)
    return None
# 5맵 GENERAL_ONLY (베이킹된 비공개 경로) + map31 NORMAL(무회귀)
cases=[("00","map10_GEN",True),("05","map31_GEN",True),("06","map61_GEN",True),("07","map71_GEN",True),("03","map161_GEN",True),("05","map31_NORMAL",False)]
tot=0;fin=0
for idx,tag,gen in cases:
    subprocess.run(["pkill","-f","my_car.py"],stderr=subprocess.DEVNULL);subprocess.run(["pkill","-f","Algo.exe"],stderr=subprocess.DEVNULL)
    r=run(idx,tag,gen)
    el=r.get('elapsed') if r else None
    line=f"{tag} {r.get('finished') if r else 'ERR'} {el} {r.get('collisions') if r else '-'}"
    open(OUT,"a").write(line+"\n");print(line)
    if gen and r and r.get('finished'): tot+=el;fin+=1
open(OUT,"a").write(f"# GENERAL 완주 {fin}/5, 총 {tot:.1f} (baseline일반 930.5, 튜닝 881)\n")
print(f"# GENERAL 완주 {fin}/5, 총 {tot:.1f}");print("DONE")
