#!/usr/bin/env python3
import argparse
import html
import json
import re
from pathlib import Path


TELEMETRY_RE = re.compile(
    r"\[Telemetry\] progress=(?P<progress>-?[0-9.]+) "
    r"speed=(?P<speed>-?[0-9.]+) "
    r"max_speed=(?P<max_speed>-?[0-9.]+) "
    r"middle=(?P<middle>-?[0-9.]+) "
    r"angle=(?P<angle>-?[0-9.]+) "
    r"steer=(?P<steer>-?[0-9.]+) "
    r"throttle=(?P<throttle>-?[0-9.]+) "
    r"brake=(?P<brake>-?[0-9.]+) "
    r"collisions=(?P<collisions>\d+) "
    r"penalties=(?P<penalties>\d+)"
)
FINISHED_RE = re.compile(r"finished return_code=(?P<return_code>-?\d+) elapsed=(?P<elapsed>[0-9.]+)s")
MAP_RE = re.compile(r"\[DrivingController\] Map : (?P<map>\d+)")


def parse_log(path):
    rows = []
    map_num = "unknown"
    elapsed = None
    for line in Path(path).read_text(errors="replace").splitlines():
        map_match = MAP_RE.search(line)
        if map_match:
            map_num = map_match.group("map")
        match = TELEMETRY_RE.search(line)
        if match:
            rows.append({key: float(value) for key, value in match.groupdict().items()})
            rows[-1]["collisions"] = int(rows[-1]["collisions"])
            rows[-1]["penalties"] = int(rows[-1]["penalties"])
        finished_match = FINISHED_RE.search(line)
        if finished_match and int(finished_match.group("return_code")) == 0:
            elapsed = float(finished_match.group("elapsed"))
    return map_num, elapsed, rows


def render_html(log_path, map_num, elapsed, rows):
    title = f"SSAFY Race Replay - Map {map_num}"
    payload = json.dumps(rows, ensure_ascii=False)
    elapsed_text = "DNF" if elapsed is None else f"{elapsed:.2f}s"
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)}</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #101114; color: #f4f5f7; }}
    header {{ display: flex; gap: 18px; align-items: center; padding: 14px 18px; border-bottom: 1px solid #2a2d33; }}
    header strong {{ font-size: 16px; }}
    header span {{ color: #b8bdc7; font-size: 13px; }}
    main {{ display: grid; grid-template-columns: 1fr 320px; min-height: calc(100vh - 54px); }}
    canvas {{ width: 100%; height: calc(100vh - 54px); background: #16191f; display: block; }}
    aside {{ border-left: 1px solid #2a2d33; padding: 16px; background: #13151a; }}
    .metric {{ display: flex; justify-content: space-between; padding: 9px 0; border-bottom: 1px solid #252830; font-size: 14px; }}
    .metric b {{ font-size: 18px; }}
    button {{ width: 100%; height: 36px; margin: 12px 0; border: 0; border-radius: 6px; background: #4f8cff; color: white; font-weight: 700; }}
    input {{ width: 100%; }}
    @media (max-width: 860px) {{ main {{ grid-template-columns: 1fr; }} aside {{ border-left: 0; border-top: 1px solid #2a2d33; }} canvas {{ height: 62vh; }} }}
  </style>
</head>
<body>
  <header>
    <strong>{html.escape(title)}</strong>
    <span>{html.escape(str(log_path))}</span>
  </header>
  <main>
    <canvas id="track"></canvas>
    <aside>
      <div class="metric"><span>Elapsed</span><b>{elapsed_text}</b></div>
      <div class="metric"><span>Progress</span><b id="progress">0%</b></div>
      <div class="metric"><span>Speed</span><b id="speed">0</b></div>
      <div class="metric"><span>Middle</span><b id="middle">0</b></div>
      <div class="metric"><span>Steer</span><b id="steer">0</b></div>
      <div class="metric"><span>Collisions</span><b id="collisions">0</b></div>
      <div class="metric"><span>Penalties</span><b id="penalties">0</b></div>
      <button id="play">Play / Pause</button>
      <input id="scrub" type="range" min="0" max="{max(0, len(rows) - 1)}" value="0" />
    </aside>
  </main>
  <script>
    const rows = {payload};
    const canvas = document.getElementById('track');
    const ctx = canvas.getContext('2d');
    const fields = ['progress', 'speed', 'middle', 'steer', 'collisions', 'penalties'];
    const scrub = document.getElementById('scrub');
    let idx = 0;
    let playing = true;

    function resize() {{
      canvas.width = canvas.clientWidth * devicePixelRatio;
      canvas.height = canvas.clientHeight * devicePixelRatio;
      draw();
    }}
    addEventListener('resize', resize);

    function yForMiddle(middle) {{
      const h = canvas.height;
      return h * 0.5 - (middle / 10) * h * 0.38;
    }}

    function draw() {{
      const w = canvas.width, h = canvas.height;
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = '#1b1f27';
      ctx.fillRect(0, h * 0.08, w, h * 0.84);
      ctx.strokeStyle = '#6f7785';
      ctx.lineWidth = 2 * devicePixelRatio;
      ctx.beginPath(); ctx.moveTo(0, h * 0.12); ctx.lineTo(w, h * 0.12); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(0, h * 0.88); ctx.lineTo(w, h * 0.88); ctx.stroke();
      ctx.strokeStyle = '#3a404b';
      ctx.setLineDash([10 * devicePixelRatio, 12 * devicePixelRatio]);
      ctx.beginPath(); ctx.moveTo(0, h * 0.5); ctx.lineTo(w, h * 0.5); ctx.stroke();
      ctx.setLineDash([]);

      ctx.strokeStyle = '#4f8cff';
      ctx.lineWidth = 3 * devicePixelRatio;
      ctx.beginPath();
      rows.slice(0, idx + 1).forEach((row, i) => {{
        const x = (row.progress / 100) * w;
        const y = yForMiddle(row.middle);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }});
      ctx.stroke();

      const row = rows[idx] || rows[0] || {{}};
      const x = ((row.progress || 0) / 100) * w;
      const y = yForMiddle(row.middle || 0);
      ctx.save();
      ctx.translate(x, y);
      ctx.rotate(((row.angle || 0) * Math.PI) / 180);
      ctx.fillStyle = '#ffcf5a';
      ctx.fillRect(-10 * devicePixelRatio, -6 * devicePixelRatio, 20 * devicePixelRatio, 12 * devicePixelRatio);
      ctx.fillStyle = '#101114';
      ctx.fillRect(3 * devicePixelRatio, -4 * devicePixelRatio, 7 * devicePixelRatio, 8 * devicePixelRatio);
      ctx.restore();

      fields.forEach((field) => {{
        const value = row[field] ?? 0;
        document.getElementById(field).textContent = field === 'progress' ? value.toFixed(2) + '%' : Number(value).toFixed(field === 'collisions' || field === 'penalties' ? 0 : 2);
      }});
      scrub.value = idx;
    }}

    document.getElementById('play').onclick = () => playing = !playing;
    scrub.oninput = () => {{ idx = Number(scrub.value); draw(); }};

    function tick() {{
      if (playing && rows.length) idx = Math.min(rows.length - 1, idx + 1);
      draw();
      requestAnimationFrame(() => setTimeout(tick, 70));
    }}
    resize();
    tick();
  </script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("log")
    parser.add_argument("-o", "--output")
    args = parser.parse_args()

    log_path = Path(args.log)
    map_num, elapsed, rows = parse_log(log_path)
    output = Path(args.output) if args.output else Path("work/replays") / f"{log_path.stem}.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(log_path, map_num, elapsed, rows), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
