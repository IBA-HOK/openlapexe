# -*- coding: utf-8 -*-
"""TDD RED: offline vs 403 branch logging distinct."""
from __future__ import annotations

import logging
import pathlib
import tempfile
import urllib.error
import urllib.request
from unittest.mock import patch

import pytest


def _isolated_fetch(mock_side_effect, caplog):
    from openlapexe.geo_tile import fetch_tile, _clear_caches_for_tests, PLACEHOLDER_PNG

    _clear_caches_for_tests()
    tmp = pathlib.Path(tempfile.mkdtemp())
    caplog.clear()
    caplog.set_level(logging.INFO, logger="openlapexe.geo_tile")
    with patch.object(urllib.request, "urlopen", side_effect=mock_side_effect):
        data = fetch_tile(10, 909, 403, base_url="https://tile.openstreetmap.org/{z}/{x}/{y}.png", cache_dir=tmp, timeout=1.0)
    _clear_caches_for_tests()
    return data, list(caplog.records), PLACEHOLDER_PNG


def test_403_branch_logs_warning_403(caplog):
    from openlapexe.geo_tile import PLACEHOLDER_PNG

    url = "https://tile.openstreetmap.org/10/909/403.png"
    err_403 = urllib.error.HTTPError(url, 403, "Forbidden", hdrs=None, fp=None)
    data, records, placeholder = _isolated_fetch(err_403, caplog)
    assert data == placeholder == PLACEHOLDER_PNG, "403 must return PLACEHOLDER_PNG without crash"
    assert len(records) >= 1, f"Expected at least 1 log record for 403, got {records}"
    msgs = " ".join(f"{r.levelname} {r.getMessage()}" for r in records)
    assert "403" in msgs, f"403 log must contain '403', got: {msgs}"
    assert any(r.levelname == "WARNING" for r in records), f"403 should be WARNING, got {[r.levelname for r in records]}"


def test_offline_branch_logs_info_offline(caplog):
    from openlapexe.geo_tile import PLACEHOLDER_PNG

    err_offline = urllib.error.URLError("offline test")
    data, records, placeholder = _isolated_fetch(err_offline, caplog)
    assert data == placeholder == PLACEHOLDER_PNG, "offline must return PLACEHOLDER_PNG without crash"
    assert len(records) >= 1, f"Expected at least 1 log record for offline, got {records}"
    msgs = " ".join(f"{r.levelname} {r.getMessage()}" for r in records)
    assert "offline" in msgs.lower(), f"offline log must contain 'offline', got: {msgs}"
    assert any(r.levelname == "INFO" for r in records), f"offline should be INFO, got {[r.levelname for r in records]}"


def test_branch_distinct_logs(caplog):
    """Offline vs 403 must produce distinct log records (not conflated)."""
    url = "https://tile.openstreetmap.org/10/909/403.png"
    err_403 = urllib.error.HTTPError(url, 403, "Forbidden", hdrs=None, fp=None)
    err_offline = urllib.error.URLError("offline test")

    _, rec_403, _ = _isolated_fetch(err_403, caplog)
    msg_403 = " ".join(r.getMessage() for r in rec_403)
    lvl_403 = [r.levelname for r in rec_403]

    _, rec_off, _ = _isolated_fetch(err_offline, caplog)
    msg_off = " ".join(r.getMessage() for r in rec_off)
    lvl_off = [r.levelname for r in rec_off]

    assert msg_403 != msg_off, f"403 vs offline log messages must differ: 403='{msg_403}' offline='{msg_off}'"
    assert lvl_403 != lvl_off or msg_403.lower() != msg_off.lower(), "Log records must be distinguishable (level or message)"
    assert "403" in msg_403
    assert "offline" in msg_off.lower()
