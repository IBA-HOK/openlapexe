# -*- coding: utf-8 -*-
"""WD.1 TDD RED: CLI --help/--headless/--validate/--dry-run/--json"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys


def _run(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    # Use python -m openlapexe with given args
    # Ensure project root cwd for data resolution
    import os

    root = pathlib.Path(__file__).resolve().parents[1]
    cmd = [sys.executable, "-m", "openlapexe", *args]
    env = os.environ.copy()
    # ensure src on PYTHONPATH for subprocess
    src = str(root / "src")
    prev = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src + (os.pathsep + prev if prev else "")
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(root) if cwd is None else cwd,
        timeout=10,
        env=env,
    )


def test_help_contains_headless():
    r = _run("--help")
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, f"--help exit {r.returncode}: {out}"
    assert "headless" in out.lower(), f"--help missing headless: {out[:500]}"
    assert "--validate" in out, f"--help missing --validate: {out[:500]}"
    assert "--dry-run" in out, f"--help missing --dry-run: {out[:500]}"
    assert "--json" in out, f"--help missing --json: {out[:500]}"
    assert "--vehicle" in out, f"--help missing --vehicle: {out[:500]}"
    assert "--track" in out, f"--help missing --track: {out[:500]}"


def test_validate_bad_exits_2_japanese():
    r = _run("--validate", "bad.json")
    assert r.returncode == 2, f"expected exit 2, got {r.returncode} stdout={r.stdout[:300]} stderr={r.stderr[:500]}"
    err = r.stderr or ""
    # Japanese path error must contain path and Japanese chars (パス or エラー or 見つかりません)
    assert "bad.json" in err, f"stderr missing path bad.json: {err[:500]}"
    has_jp = any(k in err for k in ("パス", "エラー", "見つかりません", "無効", "存在しません", "ファイル"))
    assert has_jp, f"stderr missing Japanese path error: {err[:500]}"


def test_dry_run_prints_laptime_without_file():
    # ensure no leftover output file
    root = pathlib.Path(__file__).resolve().parents[1]
    before = set(root.glob("*.csv")) | set(root.glob("*.json")) | set((root / "output").glob("*") if (root / "output").exists() else set())
    r = _run("--headless", "--vehicle", "f1", "--track", "spa", "--dry-run")
    assert r.returncode == 0, f"dry-run exit {r.returncode} stdout={r.stdout[:500]} stderr={r.stderr[:500]}"
    out = r.stdout or ""
    # should contain laptime numeric (e.g., 95.x or mm:ss or laptime keyword)
    assert "laptime" in out.lower() or "lap" in out.lower() or any(ch.isdigit() for ch in out), f"dry-run missing laptime: {out[:500]}"
    # no file created (check not creating file in cwd)
    after = set(root.glob("*.csv")) | set(root.glob("*.json")) | set((root / "output").glob("*") if (root / "output").exists() else set())
    # Filter only new files that didn't exist before and are not expected data files
    new_files = after - before
    # Exclude data files
    new_files = {p for p in new_files if p.name not in ("bad.json",) and "data" not in str(p)}
    # dry-run must not create output file
    assert len(new_files) == 0, f"dry-run created file unexpectedly: {new_files}"


def test_json_valid():
    r = _run("--headless", "--vehicle", "f1", "--track", "spa", "--dry-run", "--json")
    assert r.returncode == 0, f"--json exit {r.returncode} stdout={r.stdout[:500]} stderr={r.stderr[:500]}"
    out = (r.stdout or "").strip()
    assert out, "stdout empty for --json"
    try:
        data = json.loads(out)
    except Exception as e:
        raise AssertionError(f"stdout not valid JSON: {e}\n{out[:500]}")
    # check laptime field present
    assert isinstance(data, dict), f"JSON root not dict: {type(data)}"
    has_lap = any(k.lower() in ("laptime", "lap_time", "time", "laptime_s") for k in data.keys()) or "laptime" in str(data).lower()
    assert has_lap, f"JSON missing laptime key: {list(data.keys())[:10]} {out[:500]}"
