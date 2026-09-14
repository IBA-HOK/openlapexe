# Donington Park, Length Decision Record

**Date:** 2026-09-13
**Status:** DECISION RECORD ONLY, NO TRACK MUTATION
**Scope:** This document records the measured gap and evaluates three options. It does not modify any file under `src/`, `tests/`, or `data/tracks/`. No commits are made by this record.

---

## 1. Measured Values

| Source | File | length_m | How obtained |
|--------|------|----------|--------------|
| Racing (default) | `data/tracks/donington.json` | **3941.689 m** (3941.6889565405927 in file) | `Donington Park.xlsx` shape-data via OpenTRACK reimpl + `optimize_centerline` from centerline, half_width 5.5, margin 0.5 |
| Centerline | `data/tracks/donington_centerline.json` | **3942.045 m** | `Donington Park.xlsx` shape-data, Pchip curv, mesh 2.5 m, closed_loop true |

Reproduce:

```bash
python3 -c "import json,pathlib; print(json.loads(pathlib.Path('data/tracks/donington.json').read_text())['length_m'])"
python3 -c "import json,pathlib; print(json.loads(pathlib.Path('data/tracks/donington_centerline.json').read_text())['length_m'])"
```

---

## 2. Yardsticks

| Yardstick | Nominal | Gap vs racing 3941.689 m | Gap vs centerline 3942.045 m |
|-----------|---------|--------------------------|-------------------------------|
| **GP (FIA)** | **4020 m** | **-78.31 m / -1.95%** | **-77.96 m / -1.94%** |
| National | 3149 m (alt 3186 m quoted) | +792.69 m / +25.17% (or +755.69 m vs 3186) | +793.05 m / +25.18% |

Neither yardstick matches the current trace:

- GP gap is -78.3 m, about -1.95%, outside the usual plus/minus 1% tolerance used elsewhere (for example Spa 0.73%).
- National gap is far larger and in the opposite direction, so the trace is not a National layout either.

Conclusion: the `Donington Park.xlsx` shape-data as digitized yields about 3942 m centerline, which does not correspond to either published Donington length within tolerance. The file is kept frozen as measured, no silent scaling is applied here.

---

## 3. Options, Quantified

### Option A, Uniform stretch ×1.01978 to 4019.67 m

| Field | Value |
|-------|-------|
| factor | **1.01978** (= 4020 / 3941.689) |
| length_scaled (racing) | **4019.67 m** (3941.689 × 1.01978 = 4019.666..., rounded to 4019.67) |
| length_scaled (centerline) | 4019.79 m (3942.045 × 1.01978) |
| delta vs GP nominal | **-0.33 m / -0.008%** (4019.67 - 4020) |
| curvature effect | **curv /= 1.01978** (all radii ×1.01978, curvatures divided by factor) |
| estimated lap delta | **+0.3 s** (longer distance dominates, gentler curv slightly raises v_lat = sqrt(ay/|curv|), net small positive) |
| effort | trivial, one-line scale |
| shape fidelity | **distorts shape**, every straight and radius stretched equally, not a true GP retrace |

Pros:

- Hits GP nominal within 0.33 m.
- Zero new data collection, instant.

Cons:

- Geometrically dishonest, uniform stretch does not reproduce the real GP corner positions or radii.
- Curvature divided by 1.01978 changes every apex speed slightly, bias is systematic.
- Hides the provenance gap instead of fixing it.
- Would require rewriting both `donington.json` and `donington_centerline.json` and re-optimizing the racing line, which this record explicitly does not do.

### Option B, New FIA GP trace via Overpass (scaffold only)

| Field | Value |
|-------|-------|
| method | **Overpass API trace**, stitch `highway=raceway` / `area:highway` ways for Donington Park GP loop, same pattern as `suzuka` 68-way stitch |
| estimate | **1 to 2 days** (query, stitch, clean kink joints, mesh 2 to 2.5 m, closed_loop correction, optimize_centerline, validate) |
| expected length | about 4020 m (to be measured, not assumed) |
| accuracy | **most accurate**, true GP geometry, no uniform distortion |
| deliverable | new scaffold track pair, honest provenance with `overpass_raw.xml` kept |

Pros:

- Fixes root cause, real GP geometry.
- Consistent with Suzuka precedent (`data/reference/suzuka/overpass_raw.xml`).
- Curvature and Rmin will be measured, not scaled.

Cons:

- 1 to 2 days of work, OSM coverage for Donington must be verified (way completeness, access tags).
- New files need review, not a one-line fix.
- Scaffold only, still requires validation before it can replace the frozen trace.

### Option C, Keep 3942 frozen + mark FAIL (RECOMMENDED, DEFAULT)

| Field | Value |
|-------|-------|
| fia_status | **FAIL** (outside plus/minus 1% vs GP 4020 m, not National) |
| action | **no mutation**, keep `donington.json` 3941.689 m and `donington_centerline.json` 3942.045 m exactly as is |
| marking | record FAIL in validation / verification reports, do not scale or retrace until approved |

Pros:

- **Honest**, preserves measured provenance, no distortion.
- Zero risk, zero shape change.
- Matches the broader rule: include only if a closed length with plus/minus 1% provenance exists. Donington currently does not, so it is marked FAIL rather than silently fixed.
- Reversible, either A or B can still be approved later.

Cons:

- GP yardstick stays FAIL, Donington cannot be used for FIA GP comparisons until a later decision.
- Requires callers to handle FAIL explicitly.

---

## 4. Decision Matrix

| Criterion | A: Uniform stretch ×1.01978 | B: New Overpass GP trace | C: Keep frozen + FAIL |
|-----------|-----------------------------|--------------------------|-----------------------|
| Hits 4020 m nominal | Yes, 4019.67 m (delta -0.33 m) | Expected, to be measured | No, stays 3941.69 / 3942.05 |
| Shape fidelity | Poor, uniform distortion | **Best**, true geometry | Preserved (no change) |
| Provenance honesty | Low, hides gap | **High**, raw XML kept | **High**, marks gap honestly |
| Effort | Minutes | **1 to 2 days** | Zero |
| Risk | Silent bias (+0.3 s est, curv/=1.01978) | Stitch/kink cleanup needed | None |
| Reversible | Yes, but pollutes history | Yes, scaffold isolated | **Yes, trivially** |
| Recommended | No | Viable if GP accuracy needed | **Yes, DEFAULT** |

---

## 5. Pros / Cons Summary

- **A** trades honesty for a quick number. It reaches 4019.67 m but every radius is stretched by 1.01978 and curvature is divided by the same factor. Lap time is estimated +0.3 s longer. The method is not a retrace.
- **B** is the correct long term fix. It follows the Suzuka pattern, needs 1 to 2 days, and yields the most accurate GP trace. It is scaffold only until validated.
- **C** keeps the current files frozen and marks the GP yardstick as FAIL. This is the safest default and is recommended.

---

## 6. Approvals Required

No file under `src/`, `tests/`, or `data/tracks/` may be edited on the basis of this record alone. Each option needs an explicit checked approval:

- [ ] **APPROVAL_REQUIRED, Option A:** Approve uniform stretch ×1.01978 (curv/=1.01978, 4019.67 m, est lap +0.3 s, distorts shape). Requires explicit sign-off before any `data/tracks/donington*.json` rewrite and racing re-optimization.
- [ ] **APPROVAL_REQUIRED, Option B:** Approve new FIA GP trace via Overpass (1 to 2 days, most accurate, scaffold only). Requires explicit sign-off before starting the Overpass stitch and before any new track files are committed.
- [ ] **APPROVAL_REQUIRED, Option C:** Approve keep 3942 frozen + mark FAIL (RECOMMENDED default). Requires explicit sign-off to record FAIL in validation without mutating tracks. **DEFAULT if no box is checked.**

---

## 7. DEFAULT Statement

**DEFAULT = C.** If no approval box above is checked, the project stays on Option C: `donington.json` 3941.689 m and `donington_centerline.json` 3942.045 m remain frozen, the GP 4020 m yardstick is marked FAIL (gap -78.3 m / -1.95%), and no uniform stretch and no new trace is started. Any move to A or B requires a checked **APPROVAL_REQUIRED** box and a separate follow-up change.

---

## 8. Verification

```bash
# This record must contain 4019.67
grep -q "4019.67" AgentDoc/docs/donington_decision.md && echo "grep 4019.67 PASS"

# JSON must be valid
python3 -m json.tool data/reference/donington_options.json > /dev/null && echo "json.tool PASS"

# No track mutation (should be empty)
git diff -- src/ tests/ data/tracks/  # expect empty
```

Machine-readable options are in `data/reference/donington_options.json` with keys `{A:{factor,length_scaled,lap_delta},B:{method,estimate},C:{fia_status}}`.

---

## 9. References

- `data/tracks/donington.json` racing 3941.689 m, `data/tracks/donington_centerline.json` 3942.045 m
- `data/README.md` Tracks section, Donington row
- `AgentDoc/docs/racing_lines_all.md` half_width 5.5 for Donington
- `data/reference/suzuka/overpass_raw.xml` precedent for Option B pattern
