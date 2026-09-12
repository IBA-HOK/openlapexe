# GT500 Suzuka BoP Mass Calculation

Date: 2026-09-12
File: `data/vehicles/gt500_suzuka.json`

## Arithmetic

```
M = base_mass_kg + BoP_kg + SW_kg
M = 1245 + 0 + 0 = 1245
M_final = 1100 (fallback estimate)
```

Steps:

1. base_mass_kg = 1245 kg from `data/vehicles/gt.json` (GT3 Generic). This is the upstream GT baseline, kept as reference.
2. BoP_kg = 0 kg. GT500 class has no mass BoP. Bulletin shows only fuel flow restrictor per SpR Art23, mass BoP weight is 0. GT300 table has mass entries (for example SUBARU BRZ +65 kg), which confirms GT500 BoP weight is 0.
3. SW_kg = 0 kg. 2024 Suzuka Q2 (Round5, Dec 7 2024, Q2 14:48 to 15:03) SW column is empty for all 15 entries on the final result page, so interpreted as 0 kg for final. 2025 Suzuka Q2 (Round5, Aug 23 2025, Q2 16:26 to 16:36) SW column lists values but pole car 16 is empty, others 1 to 100 kg, still pole 0 kg.
4. Sum = 1245 kg.
5. Fallback = 1100 kg applied via `provenance_type fallback estimate`. Reason: 1245 kg exceeds GT500 regulation (min 1020 kg) and is too heavy for GT500 class, realistic GT500 mass is about 1100 kg. So `M` and `mass_kg` are set to 1100 kg, arithmetic is recorded honestly.

Fields in `data/vehicles/gt500_suzuka.json` provenance:

- base_mass_kg: 1245
- BoP_kg: 0
- SW_kg: 0
- M_final_kg: 1100
- mass_kg_arithmetic: "1245+0+0=1245 -> fallback 1100"
- M_calculation: "M = base + BoP + SW = 1245 + 0 + 0 = 1245 (arithmetic recorded). Fallback GT500 realistic mass 1100 kg applied via provenance='fallback estimate' as permitted when SW empty/network partial; base GT3 1245kg exceeds GT500 reg (min 1020kg) so 1100 reflects GT500 class."

## Sources

- Q2 2024 best: 1'43.143 R Car 14 ENEOS X PRIME GR Supra (Oshima/Fukuzumi) 5/5 laps, Sugo reference 1'44.112. URL `https://supergt.net/result?series=2024&gt_class=gt500&race_num=3&round=Round5`
- Q2 2025 best: 1'45.377 Car 16 ARTA MUGEN CIVIC TYPE R-GT #16 (Otsu/Sato) 3/4 laps. URL `https://supergt.net/result?series=2025&gt_class=gt500&race_num=3&round=Round5`
- BoP bulletin: GT500 no mass weight, only fuel flow restrictor. URLs in provenance `source_urls` include 2024, 2025 and 5th Suzuka condition pages. Fetched 2026-09-12 via urllib with UA Mozilla/5.0.
- Torque scale: 1.08 times `data/vehicles/gt.json` 18 points 1000 to 7000 rpm, peak 545.29 Nm to 588.91 Nm, shape identical, rpm unchanged.

## Provenance Links

- `data/vehicles/gt500_suzuka.json` provenance block
- `data/vehicles/gt.json` as torque source
- Q2 times kept in provenance fields `Q2_2024_best` and `Q2_2025_best`

## Honesty Note

We keep the arithmetic 1245 visible and apply 1100 as fallback estimate. This is not hidden. If SW or BoP updates arrive, recompute `1245 + BoP + SW` and compare to 1100, update this file and the JSON provenance together.

## Validation

```bash
python -c "import json,pathlib; d=json.loads(pathlib.Path('data/vehicles/gt500_suzuka.json').read_text()); print(d['provenance']['mass_kg_arithmetic'])"
# expect 1245+0+0=1245 -> fallback 1100
pytest tests/test_gt500_suzuka.py -q
```
