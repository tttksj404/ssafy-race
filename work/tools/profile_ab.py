import os,re,subprocess,json
from pathlib import Path
ROOT=Path("/Users/tttksj/Desktop/ssafy-race")
MAPS=[("00","map10"),("05","map31"),("06","map61"),("07","map71"),("03","map161")]
OUT=ROOT/"work/experiments/profile_ab.txt";open(OUT,"w").write("map fin elapsed col\n")
def run(idx,name):
    e={**os.environ,"SSAFY_GENERAL_ONLY":"1","SSAFY_AVOID_MODE":"orig","SSAFY_GEN_SPEED_PROFILE":"1"}
    for att in range(3):
        p=subprocess.run(["./work/run_experiment.sh",idx,f"pab_{name}"],cwd=str(ROOT),text=True,env=e,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=900)
        m=re.search(r"\[ExperimentLog\] (.+)",p.stdout);log=m.group(1).strip() if m else ""
        if log and Path(log).exists() and "finished return_code" in Path(log).read_text(errors="replace"):
            s=subprocess.run(["python3","work/tools/score_logs.py","--json",log],cwd=str(ROOT),text=True,stdout=subprocess.PIPE);return json.loads(s.stdout)[0]
        subprocess.run(["pkill","-f","my_car.py"],stderr=subprocess.DEVNULL);subprocess.run(["pkill","-f","Algo.exe"],stderr=subprocess.DEVNULL);import time;time.sleep(15)
    return None
tot=0;fin=0
for idx,name in MAPS:
    subprocess.run(["pkill","-f","my_car.py"],stderr=subprocess.DEVNULL);subprocess.run(["pkill","-f","Algo.exe"],stderr=subprocess.DEVNULL)
    r=run(idx,name);el=r.get('elapsed') if r else None
    open(OUT,"a").write(f"{name} {r.get('finished') if r else 'ERR'} {el} {r.get('collisions') if r else '-'}\n");print(name,r.get('finished') if r else 'ERR',el)
    if r and r.get('finished'): tot+=el;fin+=1
open(OUT,"a").write(f"# PROFILE 완주 {fin}/5, 총 {tot:.1f} (프로파일러OFF baseline 856.7)\n");print(f"# 완주{fin}/5 총{tot:.1f} vs 856.7");print("DONE")
