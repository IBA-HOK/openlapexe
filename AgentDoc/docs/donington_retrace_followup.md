# Donington Park GP Retrace — Follow-up Task (Option B Scaffold)

**Status:** `DEFERRED — scaffold only, no trace started`
**Source decision:** `AgentDoc/docs/donington_decision.md` **Option B** (new GP trace, est 1–2 days)
**FIA status of current files:** `FAIL -1.95% (National 3942m, not GP4020)` — see `data/tracks/donington.json:meta.fia_status` and `data/tracks/donington_centerline.json:meta.fia_status`

> Current `donington.json` (3941.689 m racing) and `donington_centerline.json` (3942.045 m centerline) are **frozen** as National-layout derivation (Donington Park.xlsx, 882116a). No geometry was mutated in the annotation step. This stub records the deferred follow-up.

---

## 1. Goal

Produce a **new FIA GP-layout** track pair for Donington Park at **4020 m nominal** within **±1%** (≈ 3980–4060 m):

```
data/tracks/donington_gp.json            (racing, optimized)
data/tracks/donington_gp_centerline.json (コース中心線, stitched centerline)
```

- Must satisfy `FIA 4020 m ±1%` (same tolerance used for Spa 0.73%).
- Must not overwrite `donington.json` / `donington_centerline.json` (frozen National trace).
- Honest provenance with raw source retained: `data/reference/donington/overpass_raw.xml`.

## 2. Method — Overpass API (Suzuka precedent)

Follow the **Suzuka 68-way stitch** pattern (`data/reference/suzuka/overpass_raw.xml`):

1. **Query** Overpass API for Donington Park GP loop:
   ```
   [out:xml][timeout:90];
   (
     way["highway"="raceway"](52.73,-1.38,52.77,-1.32);
     way["area:highway"](52.73,-1.38,52.77,-1.32);
   );
   out geom;
   ```
   *Bounds to be refined after inspecting OSM `highway=raceway` coverage for Donington. Verify way completeness and access tags before stitching.*

2. **Stitch** ways into a closed loop (ordered `lat/lon` → local ENU via zone, closed_loop correction).
3. **Clean** kink joints: capped `max_curv 0.3` + 3-pt XY averaging where R < 0.5 m (same as Suzuka South R0.19 fix).
4. **Mesh** at `2.0–2.5 m`, closed_loop `true`, PCHIP curvature + linear elevation/banking.
5. **Optimize** racing line via `optimize_centerline` (`half_width 5.5 m`, `width_margin 0.5 m`, `iters 60–100`).
6. **Validate**: `length_m` in `3980–4060 m`, `json.tool` clean, `closed_loop true`, baseline simulation `f1/gp/50` measured.

Deliverable is scaffold only until validated; original Donington files remain frozen.

## 3. Acceptance Criteria

- [ ] `donington_gp_centerline.json:length_m` within **4020 m ±1%** (3980–4060 m)
- [ ] `donington_gp.json:length_m` within same band (racing delta expected < 1 m vs centerline, as with Spa/Monza)
- [ ] `data/reference/donington/overpass_raw.xml` retained (raw fetch, timestamped)
- [ ] `python -m json.tool` passes on both new JSONs
- [ ] `closed_loop true`, `mesh_size_m 2.0–2.5`, `points` monotonic `s 0→L`
- [ ] Simulation `f1/donington_gp/50` produces stable laptime (report in verification report)
- [ ] Originals `donington.json` / `donington_centerline.json` remain byte-identical except for meta annotation (geometry untouched, verified via point hash)

## 4. Estimate

**1–2 days** (same as `donington_decision.md` Option B):

| Phase | Effort |
|-------|--------|
| Overpass query + stitch | 0.5 day |
| Kink cleanup + meshing + closed_loop correction | 0.5 day |
| Racing optimization + validation + report | 0.5–1 day |

*OSM coverage for Donington must be verified; if incomplete, alternative is manual KML/DXF trace.*

## 5. References

- `AgentDoc/docs/donington_decision.md` — Options A/B/C, measured gaps, Option B estimate
- `data/tracks/donington.json` 3941.689 m / `donington_centerline.json` 3942.045 m — frozen National
- `data/README.md` Tracks section — Donington row
- `AgentDoc/docs/racing_lines_all.md` — `half_width 5.5` for Donington
- `data/reference/suzuka/overpass_raw.xml` — precedent for Overpass stitch

---

*Stub created 2026-09-14 per approval `Donington=B (new GP trace = separate follow-up, scaffold only here)`.*
