# Suzuka Racing Line — Minimum-Curvature Optimization

**Date:** 2026-09-12  
**Baseline:** `data/tracks/suzuka.json` (5805.40m OSM centerline, 1200pts, 68 ways stitched, zone 6)  
**Output:** `data/tracks/suzuka_racing.json` (5799.31m, 1200pts, closed_loop true)  
**Method:** DATA-SIDE only — `src/openlapexe/curvature_opt.py::optimize_centerline` minimizing Σκ²·ds

## Method

1. Load `suzuka.json` points `xy` (1200 pts, `x`,`y` plane meters zone 6).
2. Compute unit normals from tangents (central diff, closed wrap):
   ```
   tx[i],ty[i] = normalize(xy[(i+1)%n] - xy[(i-1)%n])
   nx,ny = -ty,tx
   left_xy  = xy + n*6.0
   right_xy = xy - n*6.0
   ```
   Assumption: Suzuka width ~12m → `half_width=6.0` documented in `meta.half_width`.
   Constraint radius = w/2 - margin = `6.0 - 0.5 = 5.5m`.
3. Call `optimize_centerline(left_xy, right_xy, closed=True, iters=200, width_margin=0.5)` deterministic (fixed iters, finite-diff gradient + line search, projection to `|c-mid|≤radius`, closure `c[-1]=c[0]`).
4. Build Track: `Candidate{points_xy: center} → Track.from_candidates(mode='dxf', closed_loop=True) → save_json('suzuka_racing')` with `meta {source:'optimize_centerline min-curvature from suzuka.json', half_width:6.0, width_margin:0.5, zone:6}`.
5. `solver.py` untouched; verification via `simulate_full` only.

Performance optimization: `_arc_ds` and `_curvature_profile` vectorized (numpy roll) for 30× speedup; semantics identical (finite guard, open/closed handling).

## Verification

- Length: `5799.31m` in [5700,5900] (Δ -6.09m vs centerline 5805.40m, -0.10% — racing line slightly shorter).
- Points: 1200 (>200), closed distance 0.0m (<2m), `closed_loop:true`.
- Determinism: two `optimize_centerline` runs maxdiff 0.0; two `simulate_full` laptimes diff 0.0 (<1e-9).

## Before / After

| Vehicle | Track | freq | Laptime (sim) | Reference | Error | Note |
|---------|-------|------|---------------|-----------|-------|------|
| f1 | **suzuka** (centerline) | 50 | 119.6920896031 | 88.197 (2024 pole) | **+35.71%** | baseline OSM centerline |
| f1 | **suzuka_racing** (min-curvature) | 50 | **91.4983816658** | 88.197 | **+3.74%** | **-28.19s, -31.96pp** |
| gt500_suzuka | suzuka | 50 | 156.8454809686 | 103.143 (2024 Q2) | +52.07% | baseline |
| gt500_suzuka | suzuka_racing | 50 | 124.7011225516 | 103.143 | +20.90% | -32.14s |

Real F1 2024 pole 88.197s, 2025 pole 86.983s.  
F1/suzuka_racing vs 86.983 → +5.19% (vs 37.60% before).  
Racing line consistently faster and toward real pole; err% collapses from +35.7% to +3.7% (f1) demonstrating hypothesis: centerline excess curvature was the dominant bias.

## Repro

```bash
PYTHONPATH=src python - << 'PY'
import json, pathlib, math, numpy as np
from openlapexe.curvature_opt import optimize_centerline
from openlapexe.track import Track
p=pathlib.Path("data/tracks/suzuka.json")
xy=np.array([[float(pt["x"]),float(pt["y"])] for pt in json.loads(p.read_text(encoding="utf-8"))["points"]],dtype=float)
n=len(xy); tx=np.zeros(n); ty=np.zeros(n)
for i in range(n):
    im1=(i-1)%n; ip1=(i+1)%n; tx[i]=xy[ip1,0]-xy[im1,0]; ty[i]=xy[ip1,1]-xy[im1,1]
    norm=math.hypot(tx[i],ty[i]); tx[i]/=norm; ty[i]/=norm
nx=-ty; ny=tx; left=xy+np.column_stack([nx,ny])*6.0; right=xy-np.column_stack([nx,ny])*6.0
center,curv=optimize_centerline(left,right,closed=True,iters=200,width_margin=0.5)
track=Track.from_candidates({"points_xy":center},mode='dxf',closed_loop=True)
track.name="suzuka_racing"; track.meta.update({"source":"optimize_centerline min-curvature from suzuka.json","half_width":6.0,"width_margin":0.5,"zone":6})
track.save_json("suzuka_racing")
PY
PYTHONPATH=src python -m openlapexe --headless --vehicle f1 --track suzuka_racing --dry-run --json
PYTHONPATH=src pytest tests/test_suzuka_racing.py tests/test_data_schema.py -q
```

Solver intent: no `solver.py` edits — as requested, `solver.py` is untouched; only DATA-SIDE track generation plus numpy-only curvature optimization.

## Files

- `data/tracks/suzuka_racing.json` (generated, length 5799.31m)
- `src/openlapexe/curvature_opt.py` (vectorized `_arc_ds/_curvature_profile/_project_constraint`, deterministic)
- `tests/test_suzuka_racing.py` (file exists, length band, laptime <119.69 & >70, determinism 1e-9)
- `AgentDoc/docs/racing_line_suzuka.md` (this file) + appended §9 to `AgentDoc/docs/accuracy_suzuka_2026-09.md`
