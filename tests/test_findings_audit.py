# -*- coding: utf-8 -*-
"""TDD audit: FINDINGS_verified.md must match src/openlapexe/geo_tile.py constants.

RED phase: parses md and asserts values equal imported geo_tile constants.
Currently fails on 0.5/2.0 and single _LOCK.
"""
from __future__ import annotations

import pathlib
import re

def _read_md() -> str:
    p = pathlib.Path("FINDINGS_verified.md")
    if not p.exists():
        p = pathlib.Path(__file__).resolve().parents[1] / "FINDINGS_verified.md"
    return p.read_text(encoding="utf-8")

def _parse_interval(md: str) -> float | None:
    # Find snippet line MIN_INTERVAL: float = X
    m = re.search(r"MIN_INTERVAL\s*:\s*float\s*=\s*([0-9]+\.[0-9]+)", md)
    if m:
        return float(m.group(1))
    # fallback table form MIN_INTERVAL=0.5
    m2 = re.search(r"MIN_INTERVAL\s*=\s*([0-9]+\.[0-9]+)", md)
    if m2:
        return float(m2.group(1))
    return None

def _parse_timeout(md: str) -> float | None:
    m = re.search(r"TIMEOUT\s*:\s*float\s*=\s*([0-9]+\.[0-9]+)", md)
    if m:
        return float(m.group(1))
    m2 = re.search(r"TIMEOUT\s*=\s*([0-9]+\.[0-9]+)", md)
    if m2:
        return float(m2.group(1))
    return None

def test_findings_min_interval_matches_code() -> None:
    from openlapexe.geo_tile import MIN_INTERVAL
    md = _read_md()
    parsed = _parse_interval(md)
    assert parsed is not None, "FINDINGS_verified.md: could not parse MIN_INTERVAL value"
    assert parsed == MIN_INTERVAL, (
        f"FINDINGS_verified.md MIN_INTERVAL={parsed} != code MIN_INTERVAL={MIN_INTERVAL}. "
        f"Doc stale (expected 0.1, found 0.5 drift)."
    )

def test_findings_timeout_matches_code() -> None:
    from openlapexe.geo_tile import TIMEOUT
    md = _read_md()
    parsed = _parse_timeout(md)
    assert parsed is not None, "FINDINGS_verified.md: could not parse TIMEOUT value"
    assert parsed == TIMEOUT, (
        f"FINDINGS_verified.md TIMEOUT={parsed} != code TIMEOUT={TIMEOUT}. "
        f"Doc stale (expected 1.0, found 2.0 drift)."
    )

def test_findings_locks_split_documented() -> None:
    md = _read_md()
    from openlapexe import geo_tile
    assert hasattr(geo_tile, "_LRU_LOCK"), "code missing _LRU_LOCK"
    assert hasattr(geo_tile, "_THROTTLE_LOCK"), "code missing _THROTTLE_LOCK"
    assert geo_tile._LRU_LOCK is not geo_tile._THROTTLE_LOCK  # type: ignore[attr-defined]
    # Doc must document split as 有り, line-level check
    found_split_row = False
    for line in md.splitlines():
        if "_LRU_LOCK" in line and "_THROTTLE_LOCK" in line and "分離" in line:
            if "単一" in line:
                continue
            assert "有り" in line, f"split row should be 有り, got: {line}"
            assert "無し" not in line, f"split row still 無し (stale): {line}"
            found_split_row = True
            break
    assert found_split_row, "FINDINGS_verified.md missing _LRU_LOCK/_THROTTLE_LOCK split row"
    # Snippet must show split locks, not single _LOCK
    # Extract code block for geo_tile snippet (MAX_CACHE_ENTRIES block)
    # Require snippet contains both _LRU_LOCK and _THROTTLE_LOCK definitions
    assert "_LRU_LOCK = threading.Lock()" in md, "Doc snippet should show _LRU_LOCK = threading.Lock()"
    assert "_THROTTLE_LOCK = threading.Lock()" in md, "Doc snippet should show _THROTTLE_LOCK = threading.Lock()"
    # Single _LOCK alone should not be documented as current (stale)
    # After fix, doc should not contain single _LOCK = ... as sole lock
    # If still has single _LOCK row marked 有り, that row should now be 無し or removed
    # Check that no line claims 単一 `_LOCK` as 有り
    for line in md.splitlines():
        if "単一 `_LOCK`" in line:
            assert "無し" in line or "分離" in line, f"single _LOCK row stale, should be 無し after split: {line}"

def test_findings_placeholder_contract_documented() -> None:
    md = _read_md()
    from openlapexe.geo_tile import PLACEHOLDER_PNG
    assert isinstance(PLACEHOLDER_PNG, (bytes, bytearray)) and len(PLACEHOLDER_PNG) > 0
    assert "PLACEHOLDER_PNG" in md, "FINDINGS_verified.md missing PLACEHOLDER_PNG placeholder contract"
    has_row = False
    for line in md.splitlines():
        if "PLACEHOLDER" in line or "placeholder" in line.lower():
            if "有り" in line:
                has_row = True
                break
    assert has_row, "FINDINGS_verified.md should document placeholder as 有り (immediate return on failure)"
