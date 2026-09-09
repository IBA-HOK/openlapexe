# -*- coding: utf-8 -*-
"""WB.3 TDD RED: DXF INSERT block ref silent drop (5% lap under-estimate)."""
import math
import warnings

import pytest

from openlapexe.io_dxf import parse_dxf


def _write_dxf(path, content: str):
    path.write_text(content, encoding="utf-8")


def test_insert_block_ref_resolved_or_warn(tmp_path):
    # DXF with BLOCKS containing a LINE of length 100, ENTITIES has INSERT referencing it
    # Should yield exactly 1 candidate (LINE_0 transformed) OR a UserWarning mentioning block name.
    dxf = "\n".join(
        [
            "0",
            "SECTION",
            "2",
            "BLOCKS",
            "0",
            "BLOCK",
            "8",
            "0",
            "2",
            "MyBlock",
            "70",
            "0",
            "10",
            "0.0",
            "20",
            "0.0",
            "0",
            "LINE",
            "8",
            "0",
            "10",
            "0.0",
            "20",
            "0.0",
            "11",
            "100.0",
            "21",
            "0.0",
            "0",
            "ENDBLK",
            "8",
            "0",
            "0",
            "ENDSEC",
            "0",
            "SECTION",
            "2",
            "ENTITIES",
            "0",
            "INSERT",
            "8",
            "0",
            "2",
            "MyBlock",
            "10",
            "10.0",
            "20",
            "20.0",
            "0",
            "ENDSEC",
            "0",
            "EOF",
        ]
    )
    p = tmp_path / "insert.dxf"
    _write_dxf(p, dxf)

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        cands = parse_dxf(p)

    # Either resolved to 1 candidate with length ~100, or emitted a warning that names the block
    if len(cands) == 1:
        assert cands[0].length_m == pytest.approx(100.0, rel=1e-6)
        # INSERT translation should shift the line: original 0,0->100,0 shifted by 10,20 => 10,20->110,20
        assert cands[0].points_xy[0][0] == pytest.approx(10.0)
        assert cands[0].points_xy[0][1] == pytest.approx(20.0)
        assert cands[0].points_xy[1][0] == pytest.approx(110.0)
        assert cands[0].points_xy[1][1] == pytest.approx(20.0)
    else:
        # must have warned explicitly with block name and path
        assert len(w) >= 1, "INSERT silently dropped without candidate nor warning"
        msg = " ".join(str(x.message) for x in w)
        assert "MyBlock" in msg, f"warning must include block name, got: {msg}"
        assert str(p) in msg or "insert" in msg.lower(), f"warning must include path, got: {msg}"
        # fail to show RED when both branches missing (0 candidates and no warning)
        pytest.fail(f"Expected 1 candidate or warning with block name, got {len(cands)} cands and warnings {w}")


def test_insert_with_scale_and_rotation(tmp_path):
    # BLOCK line 10,0 -> length 10 along X; INSERT with scale 2 and rotation 90deg at 0,0
    # Expected: line 0,0->10,0 scaled x2 => 0,0->20,0 rotated 90 => 0,0->0,20 length 20 (scale preserved)
    dxf = "\n".join(
        [
            "0",
            "SECTION",
            "2",
            "BLOCKS",
            "0",
            "BLOCK",
            "2",
            "ScaledBlock",
            "10",
            "0.0",
            "20",
            "0.0",
            "0",
            "LINE",
            "10",
            "0.0",
            "20",
            "0.0",
            "11",
            "10.0",
            "21",
            "0.0",
            "0",
            "ENDBLK",
            "0",
            "ENDSEC",
            "0",
            "SECTION",
            "2",
            "ENTITIES",
            "0",
            "INSERT",
            "2",
            "ScaledBlock",
            "10",
            "0.0",
            "20",
            "0.0",
            "41",
            "2.0",
            "42",
            "2.0",
            "50",
            "90.0",
            "0",
            "ENDSEC",
            "0",
            "EOF",
        ]
    )
    p = tmp_path / "scale_rot.dxf"
    _write_dxf(p, dxf)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        cands = parse_dxf(p)
    if len(cands) == 1:
        assert cands[0].length_m == pytest.approx(20.0, rel=1e-6)
        # check rotation: second point approx 0,20
        assert cands[0].points_xy[1][0] == pytest.approx(0.0, abs=1e-6)
        assert cands[0].points_xy[1][1] == pytest.approx(20.0, abs=1e-6)
    else:
        assert len(w) >= 1
        assert "ScaledBlock" in " ".join(str(x.message) for x in w)


def test_insert_missing_block_warns_with_path_line(tmp_path, caplog):
    dxf = "\n".join(
        [
            "0",
            "SECTION",
            "2",
            "ENTITIES",
            "0",
            "INSERT",
            "2",
            "MissingBlock",
            "10",
            "0.0",
            "20",
            "0.0",
            "0",
            "ENDSEC",
            "0",
            "EOF",
        ]
    )
    p = tmp_path / "missing.dxf"
    _write_dxf(p, dxf)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        cands = parse_dxf(p)
    # Must warn (UserWarning + logging) with path:line and unsupported type name
    assert len(w) >= 1
    msg = " ".join(str(x.message) for x in w)
    assert "MissingBlock" in msg
    assert str(p) in msg  # path included
    # cands may be 0 because missing block not resolvable, but must not silently succeed
    assert len(cands) == 0


def test_unsupported_entity_warns_with_type_and_path(tmp_path):
    # Use an entity type never supported (e.g., TEXT, DIMENSION) should warn with path:line + type name
    dxf = "\n".join(
        [
            "0",
            "SECTION",
            "2",
            "ENTITIES",
            "0",
            "TEXT",
            "10",
            "0.0",
            "20",
            "0.0",
            "1",
            "hello",
            "0",
            "ENDSEC",
            "0",
            "EOF",
        ]
    )
    p = tmp_path / "unsupported.dxf"
    _write_dxf(p, dxf)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        cands = parse_dxf(p)
    assert len(w) >= 1
    msg = " ".join(str(x.message) for x in w)
    assert "TEXT" in msg
    assert str(p) in msg
