"""TDD RED: schema normalize detectors.

(1) meta.source self-reference — suzuka/asete/test reference own stem
(2) duplicate file suzuka_south (コース中心線).json
(3) mixed schema — spa/monza/donington top-level source/country without meta.zone
"""
import json
import pathlib

import pytest

TRACKS_DIR = pathlib.Path("data/tracks")


def _load(stem: str) -> dict:
    p = TRACKS_DIR / f"{stem}.json"
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# (1) meta.source self-reference
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("stem", ["suzuka", "asete", "test"])
def test_meta_source_not_self_reference(stem: str):
    """FAIL if meta.source contains 'from <own-stem>.json' instead of '*_centerline.json'."""
    data = _load(stem)
    meta = data.get("meta") or {}
    source = meta.get("source") or ""
    print(f"stem={stem} vs source={source!r}")
    # self-reference string that must NOT appear
    bad = f"from {stem}.json"
    good = f"from {stem}_centerline.json"
    # document offender clearly
    if bad in source:
        print(f"OFFENDER stem={stem} source={source!r} bad={bad!r} expected {good!r}")
    assert bad not in source, (
        f"meta.source self-reference for {stem}.json: got {source!r} "
        f"contains {bad!r} instead of {good!r}"
    )
    # also require centerline reference (so fixing bad -> good is enforced)
    assert good in source, f"{stem}.json meta.source should contain {good!r}, got {source!r}"


@pytest.mark.parametrize("stem", ["suzuka_south", "sugo_west", "spa", "monza", "donington"])
def test_meta_source_centerline_reference_for_others(stem: str):
    """Sanity: other tracks should already reference their _centerline correctly."""
    data = _load(stem)
    meta = data.get("meta") or {}
    source = meta.get("source") or ""
    print(f"stem={stem} vs source={source!r}")
    good = f"from {stem}_centerline.json"
    # For legacy spa/monza/donington centerline derivation this still holds (they should have _centerline)
    # but we allow empty meta.source for _centerline files; this test is for racing files
    assert good in source, f"{stem}.json meta.source should contain {good!r}, got {source!r}"


# ---------------------------------------------------------------------------
# (2) duplicate file with kanji
# ---------------------------------------------------------------------------
def test_no_duplicate_kanji_filename():
    """FAIL if 'suzuka_south (コース中心線).json' exists alongside _centerline."""
    files = sorted(p.name for p in TRACKS_DIR.iterdir() if p.is_file())
    print("listing data/tracks:", files)
    dup = "suzuka_south (コース中心線).json"
    canonical = "suzuka_south_centerline.json"
    has_dup = dup in files
    has_canonical = canonical in files
    print(f"dup={dup!r} present={has_dup} canonical={canonical!r} present={has_canonical}")
    if has_dup:
        print(f"OFFENDER duplicate file present: {dup!r} alongside {canonical!r}")
    assert dup not in files, (
        f"duplicate file {dup!r} exists alongside {canonical!r}; "
        f"listing={files}"
    )


# ---------------------------------------------------------------------------
# (3) mixed schema
# ---------------------------------------------------------------------------
def test_no_mixed_schema_top_level_vs_meta():
    """FAIL documenting gap: spa/monza/donington use top-level source/country without meta.zone.

    While suzuka family uses meta.* (meta.source, meta.zone, etc.).
    Print stem vs source per offender.
    """
    offenders: list[tuple[str, str | None, dict]] = []
    for stem in ["spa", "monza", "donington"]:
        data = _load(stem)
        top_source = data.get("source")
        country = data.get("country")
        meta = data.get("meta") or {}
        has_top = "source" in data or "country" in data
        has_meta_zone = "zone" in meta
        print(f"stem={stem} source={top_source!r} country={country!r} meta={meta} has_top={has_top} has_meta_zone={has_meta_zone}")
        if has_top and not has_meta_zone:
            offenders.append((stem, top_source, meta))
            print(f"OFFENDER stem={stem} vs source={top_source!r} meta={meta} — missing meta.zone but has top-level source/country")

    # Also document suzuka family as reference that DOES have meta.zone
    for stem in ["suzuka", "suzuka_south", "sugo_west", "asete", "test"]:
        data = _load(stem)
        meta = data.get("meta") or {}
        print(f"reference stem={stem} meta.zone={meta.get('zone', '__MISSING__')} meta.source={meta.get('source')!r}")

    assert not offenders, (
        f"mixed schema gap: {len(offenders)} offender(s) spa/monza/donington have "
        f"top-level source/country without meta.zone while suzuka family uses meta.* — "
        f"offenders={offenders}"
    )
