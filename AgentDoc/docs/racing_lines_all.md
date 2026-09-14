# Racing Lines, All Courses (2026-09 conversion)

**Date:** 2026-09-12  
**Scope:** all tracks under `data/tracks/*.json`  
**Method:** DATA-SIDE only, `src/openlapexe/curvature_opt.py::optimize_centerline` minimizing sum kappa squared times ds  
**Laptimes:** see `data/reference/verification_report_2026-09.json` and `AgentDoc/docs/accuracy_suzuka_2026-09.md`, do not copy numbers here (parallel test agent owns those baselines)

This is the successor to `AgentDoc/docs/racing_line_suzuka.md` (which covered suzuka only). That file stays for history. This file covers every course.

---

## 1. Naming convention

| File | Name field | Meaning |
|------|------------|---------|
| `X.json` | plain name, for example `Spa-Francorchamps`, `suzuka` | racing line, out-in-out default, annotation-free. This is what the solver and GUI load by default. |
| `X_centerline.json` | name with ` (コース中心線)` suffix, for example `Spa-Francorchamps (コース中心線)` | original centerline, annotated. Kept for reference, provenance, and delta checks. |

Before 2026-09-12, `X.json` held the centerline. After the conversion, the racing line took the plain name and the centerline moved to `X_centerline.json`. `suzuka_racing.json` was a legacy alias identical to `suzuka.json` (both 5799.31 m) and is now superseded by plain `suzuka.json`, no longer needed as a separate file.

## 2. Method

Goal: find a feasible path inside the track boundaries that minimizes total squared curvature weighted by arc length.

```
objective = sum( kappa^2 * ds )
kappa = |x' y'' - y' x''| / |p'|^3    (3-point finite difference, closed wrap if closed_loop)
ds    = 0.5 * (seg[i-1] + seg[i])     (per-point support, closure segment included)
constraint = |c - mid| <= radius
mid    = (left + right) / 2
width  = |right - left|
radius = width/2 - width_margin
```

Steps per track:

1. Load centerline `X_centerline.json` points `xy` (N points, plane meters, zone as stored).
2. Build normals from tangents (central diff, closed wrap). Offset by half_width to get left and right boundaries:
   ```
   tx, ty = normalize(xy[(i+1)%n] - xy[(i-1)%n])
   nx, ny = -ty, tx
   left  = xy + n * half_width
   right = xy - n * half_width
   ```
   half_width varies per track (see table below). This defines a corridor of total width `2 * half_width`.
3. Call `optimize_centerline(left, right, closed=True, iters=<per-track>, width_margin=0.5)`. Deterministic: fixed iteration count, finite-difference gradient (eps 1e-4), line search over `base_steps = [0.5, 0.25, 0.12, 0.06, 0.03, 0.015, 0.0075]` with two scaling passes, projection to `|c-mid| <= radius`, closure `c[-1]=c[0]`, no randomness.
4. Build Track: `Candidate{points_xy: center} -> Track.from_candidates(mode='dxf', closed_loop=True) -> save_json(X)` with `meta {source:'optimize_centerline min-curvature from X_centerline.json', half_width, width_margin, zone, iters where applicable}`.
5. No `solver.py` edits. Verification is via `simulate_full` only.

Width margin is 0.5 m everywhere, so usable half corridor is `half_width - 0.5`. For example suzuka 6.0 gives radius 5.5 m, test 4.0 gives radius 3.5 m.

Performance note: `_arc_ds` and `_curvature_profile` are vectorized with numpy roll for about 30 times speed, same math as the loop version.

## 3. Per-track parameters and lengths

Lengths are read at runtime from each JSON `length_m`. Values below are rounded for reading, exact file values are authoritative. Check with `python -c "import json,pathlib; print(json.loads(pathlib.Path('data/tracks/X.json').read_text())['length_m'])"`.

| Track file | Centerline file | half_width | width_margin | iters | length racing (m) | length centerline (m) | delta (m) | zone | Note |
|---|---|---|---|---|---|---|---|---|
| `spa.json` | `spa_centerline.json` | 6.0 | 0.5 | 60 | 6953.2473 | 6953.6110 | -0.3637 | - | F1 shape-data, small gain, centerline already radius-based |
| `monza.json` | `monza_centerline.json` | 6.0 | 0.5 | 100 | 5754.1895 | 5755.1220 | -0.9325 | - | F1 shape-data, small gain, centerline already radius-based |
| `donington.json` | `donington_centerline.json` | 5.5 | 0.5 | 60 | 3941.6890 | 3942.0450 | -0.3560 | - | F1 shape-data, small gain, centerline already radius-based |
| `suzuka.json` | `suzuka_centerline.json` | 6.0 | 0.5 | 200 | 5799.3102 | 5805.4018 | -6.0916 | 6 | Overpass 68-way stitch, `data/reference/suzuka/overpass_raw.xml`, honest 68-way source |
| `sugo_west.json` | `sugo_west_centerline.json` | 4.5 | 0.5 | 60 | 980.0141 | 982.1725 | -2.1584 | 10 | OSM way/573824373 scaled 1.03479 from raw 950.9 m to 982.17 m, scaled estimate not measured |
| `suzuka_south.json` | `suzuka_south_centerline.json` | 5.0 | 0.5 | 60 | 1259.2991 | 1263.9942 | -4.6951 | 6 | stadium-synthetic trace, synthetic approximation, not survey grade, smoothed `cap 0.3 + xy 3pt avg` |
| `test.json` | `test_centerline.json` | 4.0 | 0.5 | 60* | 643.8715 | 643.9270 | -0.0555 | 7 | small test loop, narrow 4.0 m corridor |
| `asete.json` | `asete_centerline.json` | 5.0 | 0.5 | 60* | 2058.9629 | 2063.2221 | -4.2592 | - | generic test course, zone null |

* `test.json` and `asete.json` carry `half_width` and `width_margin` in meta but no explicit `iters` field, generation used the standard 60 to 200 range. F1 entries that lack explicit zone store `zone: null` or omit it.

Legacy alias: `suzuka_racing.json` was byte-identical to `suzuka.json` (same length 5799.3102 m, same meta `source optimize_centerline min-curvature from suzuka.json`, created 2026-09-12T13:51:11.285177+00:00) and is now superseded, not a separate course.

F1 note: spa, monza, donington come from `Spa-Francorchamps.xlsx` / `Autodromo Nazionale Monza.xlsx` / `Donington Park.xlsx` shape-data via OpenTRACK reimplementation (type/R, Pchip on curv, heading cumsum, closure correction). Their centerlines already follow radius-based type/R, so the optimizer only trims a few tenths of a meter. This is honest and expected, not a bug.

## 4. Provenance per course

- **spa / monza / donington**: upstream `mc12027/OpenLAP-Lap-Time-Simulator` SHA `882116a47b5c3c57d5806924b600cb7ffbb264e1`, shape-data conversion, mesh 1 to 5 m, closed_loop true. See `data/README.md` Origin.
- **suzuka**: Overpass API 0.7.62.11, 68 `<way>` elements fetched 2026-09-12T13:09:52Z, bounds Suzuka Circuit surroundings, stitched centerline, length 5805.4018 m, zone 6. Raw source `data/reference/suzuka/overpass_raw.xml`.
- **sugo_west**: OSM way/573824373 single way, raw 950.9 m, scaled by 1.03479 to 982.1725 m to match known west course. Record honestly as scaled estimate. Zone 10. Centerline meta `source: sugo_west`, racing meta `source: optimize_centerline min-curvature from sugo_west_centerline.json`.
- **suzuka_south**: stadium area synthetic trace, manual PDF trace, not survey grade, 1263.9942 m, zone 6. Pre-fix max curv 5.14 (R 0.19 kink joint) capped to 0.3 with 3-point xy average, DATA-SIDE only. Record honestly as synthetic approximation.
- **test / asete**: local test courses, `creator_mode dxf`, created 2026-09-09 and 2026-09-10 for centerlines, racing rebuilt 2026-09-12.

## 5. What changed on disk

- Every `X.json` now holds the racing line. Its `points` are the optimized center, `name` is plain (no suffix), `meta.source` starts with `optimize_centerline min-curvature from ...`, `closed_loop` true, length slightly shorter than centerline.
- Every `X_centerline.json` holds the original centerline. Its `name` ends with ` (コース中心線)`, `meta.source` is the original source (`overpass`, `sugo_west`, `* Park.xlsx` shape-data, etc.).
- No `data/tracks/*.json` was hand-edited, only generated via `curvature_opt` plus `Track.from_candidates`.

## 6. Laptimes and accuracy

Do not copy laptime numbers here. For current numbers, read:

- `data/reference/verification_report_2026-09.json` (generated by `scripts/verify_accuracy.py`, owned by parallel test agent)
- `AgentDoc/docs/accuracy_suzuka_2026-09.md` (human-readable gate and error table, appendix notes racing default)

After the conversion, expect:

- F1 on spa/monza/donington: tiny delta versus centerline, since shape-data already encodes radii. Any speedup is small and within solver tolerance.
- F1 and gt500 on suzuka: large delta, centerline excess curvature was the dominant bias. See verification report for the exact `+35%` to `+3%` shift noted in the prior suzuka-only report `AgentDoc/docs/racing_line_suzuka.md`.
- Karts on suzuka_south / sugo_west: deltas of a few meters, visible but not dramatic.

If you need a number, run the report generator, do not hardcode.

## 7. Repro

```bash
# read lengths at runtime, never hardcode
python3 - << 'PY'
import json, pathlib, glob
for p in sorted(glob.glob("data/tracks/*.json")):
    d=json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
    print(pathlib.Path(p).name, d["length_m"], d.get("meta",{}).get("source"))
PY

# rebuild a single racing line (example suzuka, half_width 6.0, iters 200, margin 0.5)
PYTHONPATH=src python - << 'PY'
import json, pathlib, math, numpy as np
from openlapexe.curvature_opt import optimize_centerline
from openlapexe.track import Track
p=pathlib.Path("data/tracks/suzuka_centerline.json")
xy=np.array([[float(pt["x"]),float(pt["y"])] for pt in json.loads(p.read_text(encoding="utf-8"))["points"]],dtype=float)
n=len(xy)
tx=np.zeros(n); ty=np.zeros(n)
for i in range(n):
    im1=(i-1)%n; ip1=(i+1)%n; tx[i]=xy[ip1,0]-xy[im1,0]; ty[i]=xy[ip1,1]-xy[im1,1]
    norm=math.hypot(tx[i],ty[i]); tx[i]/=norm; ty[i]/=norm
nx=-ty; ny=tx; left=xy+np.column_stack([nx,ny])*6.0; right=xy-np.column_stack([nx,ny])*6.0
center,curv=optimize_centerline(left,right,closed=True,iters=200,width_margin=0.5)
track=Track.from_candidates({"points_xy":center},mode='dxf',closed_loop=True)
track.name="suzuka"; track.meta.update({"source":"optimize_centerline min-curvature from suzuka_centerline.json","half_width":6.0,"width_margin":0.5,"zone":6})
# track.save_json("suzuka")  # would overwrite, do not run unless you mean it
PY

# verify headless
PYTHONPATH=src python -m openlapexe --headless --vehicle f1 --track spa --dry-run --json
PYTHONPATH=src python scripts/verify_accuracy.py  # owned by parallel agent, rewrites verification_report_2026-09.json
```

## 8. Files

- `data/tracks/spa.json` + `spa_centerline.json`
- `data/tracks/monza.json` + `monza_centerline.json`
- `data/tracks/donington.json` + `donington_centerline.json`
- `data/tracks/suzuka.json` + `suzuka_centerline.json` (legacy `suzuka_racing.json` superseded)
- `data/tracks/sugo_west.json` + `sugo_west_centerline.json`
- `data/tracks/suzuka_south.json` + `suzuka_south_centerline.json`
- `data/tracks/test.json` + `test_centerline.json`
- `data/tracks/asete.json` + `asete_centerline.json`
- `src/openlapexe/curvature_opt.py`
- `data/reference/verification_report_2026-09.json` + `data/reference/cli_evidence.log` (test agent)
- `AgentDoc/docs/accuracy_suzuka_2026-09.md` (gates, error table, bias notes)
- `AgentDoc/docs/racing_line_suzuka.md` (suzuka-only predecessor, kept)
