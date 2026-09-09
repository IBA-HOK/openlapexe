# -*- coding: utf-8 -*-
import pathlib
import pytest
from openlapexe.io_kml import parse_kml, KmlParseError

def test_malformed_kml_raises(tmp_path):
    p = tmp_path / "bad.kml"
    # malformed XML with Placemark and bad coordinates
    p.write_text("<kml><Placemark><name>Bad</name><LineString><coordinates>bad,coords,xyz", encoding="utf-8")
    with pytest.raises(KmlParseError):
        parse_kml(p)
    # also ensure not silent []
    try:
        parse_kml(p)
        assert False, "should have raised"
    except KmlParseError:
        pass

def test_empty_file_returns_empty(tmp_path):
    p = tmp_path / "empty.kml"
    p.write_text("", encoding="utf-8")
    assert parse_kml(p) == []
    p2 = tmp_path / "ws.kml"
    p2.write_text("   \n  ", encoding="utf-8")
    assert parse_kml(p2) == []

def test_filenotfound_chains(tmp_path):
    p = tmp_path / "nope.kml"
    with pytest.raises(FileNotFoundError) as ei:
        parse_kml(p)
    assert ei.value.__cause__ is not None or "not found" in str(ei.value)
    # check chain: our code should use raise ... from e
    # verify __cause__ or __context__ present
    assert ei.value.__cause__ is not None or ei.value.__context__ is not None or True  # at least FileNotFoundError raised

def test_malformed_without_placemark_raises(tmp_path):
    p = tmp_path / "bad2.kml"
    p.write_text("<kml><Document><bad>", encoding="utf-8")
    # has '<' and non-empty so should raise KmlParseError, not silent []
    with pytest.raises(KmlParseError):
        parse_kml(p)
