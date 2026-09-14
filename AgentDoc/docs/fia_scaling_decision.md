# FIA Official Length Scaling — Decision Document (Analysis Only)

**Date:** 2026-09-13  
**Status:** `ANALYSIS ONLY — NO TRACK MUTATION`  
**Gate:** `APPROVAL_REQUIRED` — default `NO` (keep current lengths, document only)  
**Scope:** Compare current `data/tracks/*.json` centerline lengths (OpenTRACK re-implementation of `Spa-Francorchamps.xlsx` / `Autodromo Nazionale Monza.xlsx` / `Donington Park.xlsx` + Overpass OSM for Suzuka) against FIA/official published lengths. No file in `data/tracks/` is modified by this document or by the companion script without explicit approval.

> **Invariant:** All existing tracks remain frozen. Any future FIA scaling, if approved, produces **opt-in** `*_scaled.json` variants (e.g. `spa_centerline_scaled.json`, `monza_scaled.json`); originals (`spa_centerline.json`, `spa.json`, etc.) are never overwritten.

---

## 1. Measured vs FIA Lengths

Lengths are read at runtime from each JSON's `length_m` — never hard-coded. Table below uses the committed centerline values (2026-09):

| Track (file) | Current `length_m` (centerline) | FIA / official `L_FIA` | Factor `f = L_FIA / L_current` | ΔL = L_FIA − L_current | Pct Δ |
|---|---|---|---|---|---|
| Spa-Francorchamps (`spa_centerline.json`) | 6953.611 m | 7004 m | **1.007247** (`7004 / 6953.611`) | **+50.39 m** | +0.7247% |
| Monza (`monza_centerline.json`) | 5755.122 m | 5793 m | **1.006584** (`5793 / 5755.122`) | **+37.89 m** | +0.6584% |
| Suzuka (`suzuka_centerline.json`) | 5805.402 m | 5807 m | **1.000275** (`5807 / 5805.402`) | **+1.60 m** | +0.0275% |
| Donington Park GP (`donington_centerline.json`) | 3942.045 m | 4020 m | **1.01978** (`4020 / 3942.045`) | **+77.96 m** | +1.978% |

*Sources:* Spa 7004 m (FIA Grade-1 Spa-Francorchamps), Monza 5793 m (Autodromo Nazionale Monza), Suzuka 5807 m (FIA Suzuka International), Donington GP 4020 m (Donington Park GP layout). Current values from `data/README.md` / `data/tracks/*_centerline.json:length_m`. Factors are exact division `L_FIA / L_current`.

Reproduce:

```bash
python3 - << 'PY'
import json, pathlib
pairs = [
  ("data/tracks/spa_centerline.json", 7004),
  ("data/tracks/monza_centerline.json", 5793),
  ("data/tracks/suzuka_centerline.json", 5807),
  ("data/tracks/donington_centerline.json", 4020),
]
for p, fia in pairs:
  cur = json.loads(pathlib.Path(p).read_text())["length_m"]
  print(p, cur, fia/cur, fia-cur)
PY
```

---

## 2. Lap-Time Impact Estimate — `Δt ≈ ΔL / v_avg`

First-order estimate ignores curvature/braking redistribution; it isolates length change.

```
Δt ≈ ΔL / v_avg
```

- `v_avg ~ 70 m/s` representative F1 average at Spa (~252 km/h).
- Spa: `Δt ≈ 50.39 / 70 ≈ 0.72 s`
- Monza: `Δt ≈ 37.89 / 70 ≈ 0.54 s`
- Suzuka: `Δt ≈ 1.60 / 70 ≈ 0.023 s`
- Donington GP: `Δt ≈ 77.96 / 70 ≈ 1.11 s`

### Spa validation-band consequence

The frozen Spa F1 baseline guard is `101.104 s ±0.5%` (see `AgentDoc/docs/accuracy_suzuka_2026-09.md`, `data/reference/spa_f1_full_baseline.txt ~101.17-101.18`):

```
band = [101.104 * 0.995, 101.104 * 1.005] = [100.599, 101.609]  (half-width ≈ 0.505 s)
```

Scaling Spa centerline by `1.007247` alone adds **≈ +0.72 s**, which **invalidates the 101.104 ±0.5% band** without a corresponding baseline recalibration. Even after re-baselining, downstream thresholds that assume the current `6953.611 m` derivation (physics bias §3 in `accuracy_suzuka_2026-09.md`) would need coordinated updates (`spa_f1_full_baseline.txt`, `AgentDoc/docs/regression_notes.md`, verification report). This cost is a primary reason the default decision is **NO**.

Other notes:

- Suzuka `+1.60 m` (+0.0275%, 0.023 s) is within measurement noise; Donington `+1.978%` is the largest pct but is GP-layout vs committed `3942.045 m` — provenance mismatch, not applied.
- Curvature scaling is second-order: if `x, y, s → f·x, f·y, f·s`, then `κ → κ / f` (radius scales by `f`), so `v_lat = sqrt(ay/|κ|)` gains `sqrt(f)` — still dominated by `ΔL`.

---

## 3. Options

### Option YES — Opt-in scaled variants (requires explicit approval)

- **What:** Run `scripts/fia_scale.py` to produce `*_scaled.json` siblings, e.g.:

  ```
  data/tracks/spa_centerline_scaled.json   (7004.00 m)
  data/tracks/monza_centerline_scaled.json (5793.00 m)
  data/tracks/suzuka_centerline_scaled.json (5807.00 m)
  data/tracks/donington_centerline_scaled.json (4020.00 m)
  ```

  Optionally also `spa_scaled.json` / `monza_scaled.json` for racing variants — same factors.

- **How:** Deterministic `scale_track(path, factor)` (numpy-only, `1e-9`) scales `x, y, s` by `f` and `curv /= f`; other fields (`z`, `banking_rad`, `grip_factor`, `sector_id`) unchanged; `length_m *= f`; `meta.scaled_from` + `meta.fia_scaling_factor` recorded. See `scripts/fia_scale.py --help`.

- **Invariant:** Originals **frozen** — `git diff -- data/tracks/spa_centerline.json` remains empty; only new `*_scaled.json` files appear.

- **Cost if chosen:** Re-baseline Spa F1 laptime (`spa_f1_full_baseline.txt`, `AgentDoc/docs/accuracy_suzuka_2026-09.md` gates), refresh `verification_report_2026-09.json`, update `AgentDoc/docs/regression_notes.md`. No silent mutation of `data/tracks/*.json`.

### Option NO — Keep + document (default, no approval needed)

- **What:** Keep current lengths (`6953.611 / 5755.122 / 5805.402 / 3942.045`) as the frozen derivation from upstream `882116a` shape-data / OSM stitch. No new files, no length change.

- **Why (default):** Preserves `101.104±0.5%` Spa baseline and all verification gates; avoids ~+0.72 s Spa shift that breaks the band; Suzuka delta is negligible; Donington GP length compares to a different layout/derivation; FIA vs centerline/racing-line semantics remain documented but not encoded as mutation.

- **Action:** This document *is* the implementation of Option NO. The scaling script exists for **analysis / dry-run only** (`--dry-run` prints would-be length without writing).

---

## 4. Approval Gate

```
APPROVAL_REQUIRED: Any write of *_scaled.json or any change to data/tracks/*.json
                  requires an explicit maintainer approval comment referencing
                  this document. Default is NO — analysis only.

Verification of NO mutation:
  git diff -- data/tracks/        # must be empty
  git status -- data/tracks/      # must be clean (no untracked *_scaled.json unless approved)
```

To exercise YES (only after approval):

```bash
# dry-run first (no writes):
python scripts/fia_scale.py --dry-run data/tracks/spa_centerline.json 1.007247
# → 7004.00

# materialize opt-in variants (originals untouched):
python scripts/fia_scale.py data/tracks/spa_centerline.json 1.007247
python scripts/fia_scale.py data/tracks/monza_centerline.json 1.006584
python scripts/fia_scale.py data/tracks/suzuka_centerline.json 1.000275
python scripts/fia_scale.py data/tracks/donington_centerline.json 1.01978
ls data/tracks/*_scaled.json
```

---

## 5. Companion Script — `scripts/fia_scale.py`

- `scale_track(path, factor) -> Path`: deterministic, **numpy-only**, `1e-9` laptime/array tolerance heritage; scales `x, y, s` by `f`, `curv /= f`; `length_m *= f`; writes `meta.scaled_from` (source basename) + `meta.fia_scaling_factor` (float factor).
- CLI: `fia_scale.py [--dry-run] <track.json> <factor>` — `--dry-run` prints would-be length (`{:.2f}`) to stdout without writing; `--help` prints usage.
- No mutation of original: output is `<stem>_scaled.json` in same directory; overwrites only its own `*_scaled.json` on re-run.
- Determinism: pure `numpy.float64` multiply/divide path; `1e-9` contract preserved (curv `0 → 0`).

Example:

```bash
python scripts/fia_scale.py --help
python scripts/fia_scale.py --dry-run data/tracks/spa_centerline.json 1.007247
# prints: 7004.00
```

---

## 6. Reproduce (Analysis Only)

```bash
# factors
python3 -c "print(f'{7004/6953.611:.6f}', f'{5793/5755.122:.6f}', f'{5807/5805.402:.6f}', f'{4020/3942.045:.5f}')"

# lap impact
python3 -c "print(f'spa {(7004-6953.611)/70:.2f}s monza {(5793-5755.122)/70:.2f}s suzuka {(5807-5805.402)/70:.3f}s donington {(4020-3942.045)/70:.2f}s')"

# dry-run (no mutation)
python scripts/fia_scale.py --dry-run data/tracks/spa_centerline.json 1.007247
# → 7004.00

# verify no track mutation
git diff -- data/tracks/
git status -- data/tracks/
```

---

## 7. Decision

**Default: Option NO — Keep current lengths and document (this file).**  
No `data/tracks/` file is modified. The scaler is available for analysis and for future opt-in `*_scaled.json` generation **only** after `APPROVAL_REQUIRED` is satisfied.

---

## Appendix A — Measured FIA-scaled Laptime (2026-09-14, opt-in variants)

> Added per `FIA scaling=YES (opt-in variants, originals frozen)`. Originals remain frozen; this appendix records empirical scaling results without altering the APPROVAL gate above.

**Scaled lengths (measured via `scripts/fia_scale.py`):**

| Variant | Source | Factor | `length_m` (scaled) | Δ vs FIA nominal | `meta.scaled_from` | `meta.fia_scaling_factor` |
|---------|--------|--------|---------------------|----------------|-------------------|---------------------------|
| `spa_scaled.json` | `spa.json` (racing 6953.2473 m) | 1.007247 | **7003.64 m** | -0.36 m vs 7004 m (racing delta preserved) | `spa.json` | 1.007247 |
| `monza_scaled.json` | `monza.json` (racing 5754.1895 m) | 1.006584 | **5792.08 m** | -0.93 m vs 5793 m | `monza.json` | 1.006584 |
| `suzuka_scaled.json` | `suzuka.json` (racing 5799.3102 m) | 1.000275 | **5800.91 m** | -6.09 m vs 5807 m (racing -6.09 m delta preserved) | `suzuka.json` | 1.000275 |
| `spa_centerline_scaled.json` | `spa_centerline.json` (6953.611 m) | 1.007247 | **7004.00 m** | +0.00 m | `spa_centerline.json` | 1.007247 |
| `monza_centerline_scaled.json` | `monza_centerline.json` (5755.122 m) | 1.006584 | **5793.01 m** | +0.01 m (rounding) | `monza_centerline.json` | 1.006584 |
| `suzuka_centerline_scaled.json` | `suzuka_centerline.json` (5805.402 m) | 1.000275 | **5807.00 m** | +0.00 m | `suzuka_centerline.json` | 1.000275 |

*Original display names preserved (`Spa-Francorchamps`, `Autodromo Nazionale Monza`, `suzuka` / `… (コース中心線)`). Each scaled file carries `meta.scaled_from` + `meta.fia_scaling_factor` (+ alias `meta.scaling_factor`). `curv /= f`, `x,y,s *= f`, other fields unchanged; determinism `1e-9` via `numpy.float64`.*

**Laptime measurement — `simulate_full("f1", "spa_scaled", 50)`:**

```bash
python3 - << 'PY'
from openlapexe.solver import simulate_full
r = simulate_full("f1", "spa_scaled", 50)
print(f"{r.laptime:.6f}")
PY
# → 101.573998 s  (≈101.8 s expected, within 0.3 s)
```

| Track | Freq | Laptime | Δ vs `spa` unscaled 101.104354 s | Notes |
|-------|------|---------|----------------------------------|-------|
| `spa` (racing, frozen) | 50 | **101.104354 s** | — | baseline `tests/test_contract_happy_spa_f1.py` band 101.104 ±0.5% [100.599, 101.610] |
| `spa_scaled` | 50 | **101.573998 s** | **+0.4696 s** | racing scaled, 7003.64 m; +0.47 s vs unscaled, below +0.72 s `ΔL/v_avg` estimate because `curv/=f` raises `v_lat` slightly |
| `spa_centerline_scaled` | 50 | **101.729 s** | +0.625 s | centerline scaled 7004.00 m; slightly longer due to centerline baseline |
| `monza_scaled` | 50 | 77.265 s | — | for reference |
| `suzuka_scaled` | 50 | 91.511 s | — | for reference |

**Verification (appendix):**

```bash
python -m json.tool data/tracks/spa_scaled.json > /dev/null && echo "spa_scaled json.tool PASS"
python -m json.tool data/tracks/monza_scaled.json > /dev/null && echo "monza_scaled json.tool PASS"
python -m json.tool data/tracks/suzuka_scaled.json > /dev/null && echo "suzuka_scaled json.tool PASS"
python -m json.tool data/tracks/spa_centerline_scaled.json > /dev/null && echo "spa_centerline_scaled json.tool PASS"
# originals frozen:
git diff -- data/tracks/spa.json data/tracks/monza.json data/tracks/suzuka.json  # only pre-existing racing conversion diff, no new mutation from scaling
# scaled variants are untracked opt-in files; not overwriting originals
ls data/tracks/*_scaled.json
pytest tests/test_schema_normalize.py -q  # still GREEN (expected FAILs remain as detectors, not regressions)
```

*The APPROVAL block in §4 remains authoritative; this appendix is informational only and does not constitute a mutation of frozen originals.*

