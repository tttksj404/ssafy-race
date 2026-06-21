# 하드코딩 일반화 감사 (2026-06-21) — 비공개 테스트 맵 대비

## 결론(verdict)
BLUNT VERDICT: the general (map-agnostic) path would NOT reliably finish an arbitrary unseen map; it is brittle and tuned-to-seen-tracks, not robust. (a) Gap-finder avoidance (min(ob_line,key=target_cost)) uses a FIXED 2.25m clearance with no car-width/speed margin, prefers the nearest gap over the widest, scans only 2 obstacle clusters, truncates the usable width, and on a no-gap frame silently falls back to a STALE candidate line and stops scanning -> clips obstacles on narrow/dense unseen fields. (b) Speed tiers read the curve angle from only ~0-30m ahead (tg = speed-band index, not a true lookahead), so at high speed it systematically UNDER-BRAKES into short/blind corners; the staircase assumes the seen tracks' grip and will over-speed tighter/lower-grip unseen corners. (c) General recovery is open-loop fixed-frame reverse-then-forward with NO mid-maneuver feedback and a committed direction (the better map71 emergency net is map-guarded and dead) -> prone to wedging/oscillating/stalling. (d) Steering uses fixed hand-tuned gains, a curvature law whose radius term can blow up near the edge, a slew-rate limit that can't reach the needed angle in time at speed, and a high-speed steer clamp (0.58 at >150) that can PHYSICALLY PREVENT a required dodge. CRITICAL LANDMINE: many seg_* tuning branches AND a full-lock block (line 915: |middle|>0.74*width during lap 32.8-34.6% -> steering=+/-1.0) are gated ONLY on lap_progress, not map, so they MIS-FIRE on an unseen map's geometry, including a full-lock toward center that can throw the car across the track. Net: it may complete a benign, geometrically-similar unseen map, but on anything with tight blind corners, narrow corridors, dense obstacles, or low grip it is likely to clip, over-speed, full-lock mis-fire, or get stuck in recovery.

## 무가드 하드코딩 (비공개 맵서도 발동 = 위험)
- **L137-139 (if lap >= 90.0 and lap <= 97.2)** [HARMFUL] Shrinks recognized half_road_limit_used by 1.25 for ANY map at progress 90-97.2%, narrowing the usable road (affects edge penalties, curve radius, recovery thresholds, target clamps) on the final stretch. (unseen발동:True)
- **L154 seg_2729 = (25.2<=lap<=30.0); used L803-805** [HARMFUL] When abs_ang<25 and abs(middle)<8.5, forces target_speed up to >=140 km/h at progress 25.2-30%. (unseen발동:True)
- **L155 seg_0510 = (5.0<=lap<=10.0); used L783-785** [HARMFUL] Caps target_speed at 150 km/h during progress 5-10%. (unseen발동:True)
- **L156 seg_1783 = (17.0<=lap<=18.4); used L787-789** [HARMFUL] Caps target_speed at 75 km/h during progress 17-18.4%. (unseen발동:True)
- **L157 seg_3339 = (32.95<=lap<=33.45); used L549-551, L664-666, L859-860** [HARMFUL] Scales down middle_add (steer-correction), scales steering (*0.88 on non-61), and reduces max_delta to 0.14 at progress 32.95-33.45%. (unseen발동:True)
- **L158 seg_9283 = (92.45<=lap<=93.25); used L470-485, L557-558, L668-673, L794-796, L861-862** [HARMFUL] At progress 92.45-93.25% on EVERY map: clamps target-offset step rate, hard-clamps target to >=-7.0, scales middle_add *0.1, clamps left steering to >=-0.55 (caps left turn), adds +0.12 right bias when middle<-6, reduces target_speed by 30 (floor 60), reduces max_delta to 0.16. (unseen발동:True)
- **L159 seg_6767 = (67.3<=lap<=68.1); used L807-808** [HARMFUL] Forces target_speed = max(60, target_speed*0.7) at progress 67.3-68.1%, i.e. ~30% speed cut. (unseen발동:True)
- **L160 seg_5354 = (53.0<=lap<=53.4); used L810-811** [HARMFUL] Forces target_speed = max(60, target_speed*0.65) at progress 53.0-53.4%, ~35% speed cut. (unseen발동:True)
- **L161 seg_5444 = (53.41<=lap<=54.7); used L801-802** [HARMFUL] Forces target_speed up to >=140 km/h (speed FLOOR) at progress 53.41-54.7%. (unseen발동:True)
- **L162 seg_9898 = (98.0<=lap<=98.2); used L554-556, L798-800** [HARMFUL] Scales middle_add *1.2 (more steer correction) and target_speed *0.8 at progress 98.0-98.2%. (unseen발동:True)
- **L163 seg_8791 = (87.4<=lap<=91.8); used L920-923** [HARMFUL] When middle<-8.0, forces steering >= 0.50 (or 0.42 if spd<35), throttle=1, brake=0 at progress 87.4-91.8%. (unseen발동:True)
- **L194-198 seg_8790_left_gate (87.4<=lap<=90.25 + middle<-3.0 + obstacle cond); used L487-488, L674-677, L812-813** [HARMFUL] Clamps target into [-6.5,-6.0] (forces left lane), forces steering<=-0.04 + throttle when middle>-5.6, and raises target_speed floor to 112/92 at progress 87.4-90.25%. (unseen발동:True)
- **L729-730 (if lap < 0.5 and abs(middle)>2.0, inside spd<5 block)** [HARMLESS] At race start (<0.5%) with low speed and off-center, forces steering -0.28/+0.28 toward center. (unseen발동:True)
- **L915-918 (elif 32.8<=lap<=34.6 and abs(middle)>half_load_width*0.74)** [HARMFUL] Fallback (when not map61): forces FULL-LOCK steering -1.0/+1.0 toward center, throttle=1, brake=0 at progress 32.8-34.6% when near the edge. (unseen발동:True)

## 제거·일반화 계획
All three audits are verified against the actual file. The line numbers, the unguarded `seg_*` flags (L154-163), the road-shrink (L137-138), and the full-lock fallback (L915-918) are exactly as described. Producing the plan.

---

# REMEDIATION PLAN — my_car.py general-robustness

## 1. HARMFUL hardcoding to REMOVE first (ranked by danger on unseen maps)

All are gated on `lap%` only, no `map_num`. Delete the flag or wrap in `if map_num in ("61","71","161")`.

1. **L915-918 full-lock fallback** — `±1.0` steer + full throttle toward center at 32.8-34.6% when near edge. Can throw car across track. **Delete the terminal `elif`** (the map61 branches above it stay).
2. **L158 / L470-485,557,668,794,861 seg_9283** — clamps target ≥-7.0, caps left steer at -0.55, +right bias, -30 speed at ~92.8%. Suppresses a needed left turn. **Delete flag.**
3. **L163 / L920-923 seg_8791** — forces right steer ≥0.50 + full throttle when `middle<-8.0` in 87-92%. Fights planner into a wall. **Delete flag.**
4. **L194-198 seg_8790_left_gate** — clamps target to [-6.5,-6.0] + speed floor 112/92. Forces a lane. **Add `map_num=="31"` guard** (comment claims Map31 but no guard exists in file).
5. **L137-138 road-width shrink** (`half_road_limit_used -= 1.25` at 90-97.2%) — narrows real geometry everywhere. **Delete** (or guard).
6. **Speed caps/floors L155,156,159,160,161,162,154** (seg_0510:150, seg_1783:75, seg_6767:×0.7, seg_5354:×0.65, seg_9898:×0.8, seg_5444:140, seg_2729:140) — arbitrary fixed-progress speed overrides. **Delete all.**
7. **L157 seg_3339** (steer×0.88, Δ-cap 0.14) — low harm (damping only) but unguarded. Delete.

## 2. GENERAL algorithm weaknesses → concrete fixes

- **Avoidance clearance (L225 ped=2.25 fixed):** make `ped = car_half_width + speed*closing_factor` (dynamic margin). On empty `ob_line` (L235) do NOT fall back to stale `ob_line2`+break — instead **hard-brake and widen scan**. Remove the L242 2-cluster early-cut; carve **all** obstacles within react_dist.
- **Cost prefers nearest gap (L450):** change cost to favor **widest surviving gap** (penalize candidates whose neighbors are blocked), not `abs(x-middle)`. Fix the asymmetric `int(W)*10` truncation (L182) so target can reach the true outer edge.
- **Speed lookahead too short (L751):** set target from the **max angle over a true distance horizon** (e.g. angles[0..N] spanning ~braking-distance = `v²/2a`), not the single speed-band index. Add a conservative grip de-rate (e.g. ×0.85 on all tiers) so unseen lower-grip corners don't over-speed.
- **Recovery is open-loop & map71-only (L1088 dead on unseen):** make the general recovery (L1045) **re-evaluate `recovery_dir` each frame** from current heading/edge, exit on heading-aligned (not just spd>18), and add a collision-during-maneuver check so it doesn't re-wedge.
- **Steer clamp 0.58 at >150 (L875-889):** make the high-speed clamp **conditional on no active avoidance** — if a dodge is required, allow the larger steer (slowing is the speed controller's job, but don't physically block the turn).

## 3. VERIFY generalization WITHOUT unseen maps

- **Hold-out (primary):** strip ALL `map_num=="61/71/161/31"` blocks + every `seg_*`, run the pure general path on each of the 5 known maps. **Any map that now DNFs marks a real general-path gap**, not a tuning gap. This is the closest proxy to "unseen."
- **Leave-one-out:** keep map-specific tuning for 4 maps, run the general path (specials disabled) on the 5th; rotate. Finishing all 5 this way ≈ robust.
- **Geometry-perturbation:** add ±10-20% noise to waypoint angles / track width on a known map and re-run; fragile speed-tier and steer-gain regressions surface as off-track events.
- **Invariant asserts:** no steering command may flip to opposite full-lock within N frames unless `|angle|>55`; target must stay within `±half_load_width`.

## 4. VERDICT

**No — not reliably as-is.** It may finish a benign, geometry-similar unseen map, but the lap-%-only landmines (esp. L915 full-lock, seg_9283, seg_8791) plus short-lookahead under-braking and fixed-clearance avoidance make tight/narrow/dense/low-grip unseen maps likely to full-lock-cross, over-speed, clip, or wedge in recovery.

**Single highest-priority fix:** delete the **L915-918 full-lock fallback** (and all unguarded `seg_*` at L154-163). It is a pure correctness regression — it can slam ±1.0 lock toward center mid-corner on any unseen map. Removing it costs nothing on known maps (their behavior is in the map61-guarded branches above) and removes the worst loss-of-control trigger.

Verified file: `/Users/tttksj/Desktop/ssafy-race/submissions/my_car.py` (1319 lines).
