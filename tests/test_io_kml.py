# -*- coding: utf-8 -*-
"""tests for openlapexe.io_kml - RED->GREEN coverage per TASK."""
import math
import pathlib
import tempfile

import pytest

from openlapexe.io_kml import Candidate, parse_kml


def _hav(lon1, lat1, lon2, lat2):
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return R * c


def test_parse_kml_linestring(tmp_path):
    kml = """<?xml version="1.0" encoding="UTF-8"?>
<kml><Document><Placemark><name>Line A</name><LineString><coordinates>139.0,35.0,0 139.001,35.0,10</coordinates></LineString></Placemark></Document></kml>"""
    p = tmp_path / "a.kml"
    p.write_text(kml, encoding="utf-8")
    res = parse_kml(p)
    assert len(res) == 1
    c = res[0]
    assert isinstance(c, Candidate)
    assert c.name == "Line A"
    assert c.points_lonlat == [(139.0, 35.0), (139.001, 35.0)]
    # alt ignored -> same as hav between those two
    assert c.length_m == pytest.approx(_hav(139.0, 35.0, 139.001, 35.0), rel=1e-9)
    # kind should be LineString
    assert c.kind == "LineString"


def test_parse_kml_multigeometry_2(tmp_path):
    kml = """<?xml version="1.0" encoding="UTF-8"?>
<kml><Document><Placemark><name>Multi</name><MultiGeometry>
<LineString><coordinates>139.0,35.0,0 139.001,35.0,0</coordinates></LineString>
<LineString><coordinates>139.001,35.0,0 139.002,35.0,0</coordinates></LineString>
</MultiGeometry></Placemark></Document></kml>"""
    p = tmp_path / "b.kml"
    p.write_text(kml, encoding="utf-8")
    res = parse_kml(p)
    assert len(res) == 1
    c = res[0]
    assert c.kind == "MultiGeometry"
    # integrated points: 4 points (2+2) or 3 deduped? Our impl gives 4 with duplicate middle
    # Accept either 3 or 4 as long as length correct and points count >=3
    assert len(c.points_lonlat) in (3, 4)
    # length should be distance of two segments
    expected = _hav(139.0, 35.0, 139.001, 35.0) + _hav(139.001, 35.0, 139.002, 35.0)
    assert c.length_m == pytest.approx(expected, rel=1e-9)


def test_parse_kml_gx_track_3coords(tmp_path):
    kml = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2"><Document><Placemark><name>Track A</name><gx:Track><gx:coord>139.0 35.0 10</gx:coord><gx:coord>139.001 35.0 20</gx:coord><gx:coord>139.002 35.0 30</gx:coord></gx:Track></Placemark></Document></kml>"""
    p = tmp_path / "c.kml"
    p.write_text(kml, encoding="utf-8")
    res = parse_kml(p)
    assert len(res) == 1
    c = res[0]
    assert c.points_lonlat == [(139.0, 35.0), (139.001, 35.0), (139.002, 35.0)]
    expected = _hav(139.0, 35.0, 139.001, 35.0) + _hav(139.001, 35.0, 139.002, 35.0)
    assert c.length_m == pytest.approx(expected, rel=1e-9)
    assert c.kind == "Track"


def test_parse_kml_namespaced(tmp_path):
    kml = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><name>NS</name><LineString><coordinates>139.0,35.0,0 139.001,35.001,0</coordinates></LineString></Placemark></Document></kml>"""
    p = tmp_path / "d.kml"
    p.write_text(kml, encoding="utf-8")
    res = parse_kml(p)
    assert len(res) == 1
    assert res[0].name == "NS"
    assert len(res[0].points_lonlat) == 2


def test_parse_kml_empty_no_crash(tmp_path):
    p = tmp_path / "empty.kml"
    p.write_text("", encoding="utf-8")
    res = parse_kml(p)
    assert res == []
    # also test KML with no Placemark
    p2 = tmp_path / "n Placemark.kml"
    p2.write_text("""<?xml version="1.0" encoding="UTF-8"?><kml><Document></Document></kml>""", encoding="utf-8")
    assert parse_kml(p2) == []


def test_parse_kml_alt_ignored(tmp_path):
    kml = """<kml><Placemark><name>Alt</name><LineString><coordinates>139.0,35.0,9999 139.001,35.0,-100</coordinates></LineString></Placemark></kml>"""
    p = tmp_path / "alt.kml"
    p.write_text(kml, encoding="utf-8")
    res = parse_kml(p)
    assert res[0].points_lonlat == [(139.0, 35.0), (139.001, 35.0)]

def test_parse_kml_deterministic(tmp_path):
    kml = """<kml><Placemark><name>D</name><LineString><coordinates>139.0,35.0,0 139.001,35.0,0</coordinates></LineString></Placemark></kml>"""
    p = tmp_path / "det.kml"
    p.write_text(kml, encoding="utf-8")
    r1 = parse_kml(p)
    r2 = parse_kml(p)
    assert r1[0].points_lonlat == r2[0].points_lonlat
    assert r1[0].length_m == pytest.approx(r2[0].length_m)
