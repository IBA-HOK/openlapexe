# AgentDoc — AI-used docs index

All docs previously under `docs/`, root, and `data/reference/*.md` are consolidated here.

## Layout

- `AgentDoc/docs/` — project docs (mirrors former `docs/`)
- `AgentDoc/reference/` — reference calculation docs (mirrors `data/reference/*.md`)
- `AgentDoc/FINDINGS_verified.md` — audit findings (formerly root)
- `AgentDoc/FOLLOW_UP.md` — follow-up candidates (formerly root)

## Index

| Path | Summary |
|------|---------|
| `AgentDoc/docs/accuracy_suzuka_2026-09.md` | Suzuka 2026-09 accuracy verification: F1/GT500/kart error table, bias report, gates, and racing-line appendix |
| `AgentDoc/docs/data_validation_report.md` | Data validation report: FIA yardsticks vs frozen `f1.json`/`spa.json`, baseline provenance and solver-dominance evidence |
| `AgentDoc/docs/donington_decision.md` | Donington Park layout decision: GP vs National gap analysis, three options, Option C DEFAULT (annotated FAIL, deferred GP retrace) |
| `AgentDoc/docs/donington_retrace_followup.md` | Deferred Donington GP retrace scaffold: Overpass 68-way precedent, estimate 1–2 days, task breakdown |
| `AgentDoc/docs/fia_scaling_decision.md` | FIA scaling decision: NO as default, YES opt-in `*_scaled.json` siblings (spa/monza/suzuka ×1.007247/1.006584/1.000275) |
| `AgentDoc/docs/graph_placement.md` | Graph placement spec: per-tab chart_notebook/graph_notebook layout (Sim 9 / Drag 15 / Track 6 / Vehicle 4), no duplication |
| `AgentDoc/docs/racing_line_suzuka.md` | Suzuka-only racing line: out-in-out `optimize_centerline` on 68-way Overpass stitch, before/after laptime delta |
| `AgentDoc/docs/racing_lines_all.md` | All-tracks racing lines: 8 courses × half_width/iters, method (`sum kappa²·ds`), 22-file length table |
| `AgentDoc/docs/regression_notes.md` | Regression notes: quartic apex solver + Wd/ellipse + `ax_drag` corrections, 101.178 s / 95.8059 s baselines |
| `AgentDoc/FINDINGS_verified.md` | Line-number audit of `geo_tile.py`/`osm_canvas.py`/`course_creator.py`/`shell.py` (MIN_INTERVAL, TIMEOUT, locks, placeholder) |
| `AgentDoc/FOLLOW_UP.md` | V2 improvement candidates (GUI/vehicle/solver/track) — enumeration only, no implementation |
| `AgentDoc/reference/gt500_suzuka_bop_calc.md` | GT500 Suzuka BoP mass calc: `1245+0+0=1245 → fallback 1100` kg, Q2 2024 1'43.143 / 2025 1'45.377 |
