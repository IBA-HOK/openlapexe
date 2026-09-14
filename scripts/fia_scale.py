#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fia_scale — FIA length scaling (analysis only, deterministic, numpy-only).

Deterministic scale_track(path, factor):
  - scales x, y, s by factor (f)
  - curv /= f  (0 stays 0, preserves straight)
  - length_m *= f
  - writes meta.scaled_from + meta.fia_scaling_factor
  - numpy float64 path, 1e-9 determinism contract (numpy-only, stdlib)
  - original file is never overwritten; output is <stem>_scaled.json

CLI:
  fia_scale.py [--dry-run] <track.json> <factor>
  --dry-run prints would-be length (2 decimals) without writing
  --help works

Examples:
  python scripts/fia_scale.py --dry-run data/tracks/spa_centerline.json 1.007247  # -> 7004.00
  python scripts/fia_scale.py data/tracks/spa_centerline.json 1.007247
  python scripts/fia_scale.py --help
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _resolve_track_path(raw: str) -> pathlib.Path:
    p = pathlib.Path(raw)
    if p.exists():
        return p
    # try relative to repo root
    cand = ROOT / raw
    if cand.exists():
        return cand
    # try data/tracks/<raw> and <raw>.json
    for prefix in [ROOT / "data" / "tracks", pathlib.Path("data/tracks")]:
        for suffix in ["", ".json"]:
            cand2 = prefix / f"{raw}{suffix}"
            if cand2.exists():
                return cand2
            # also handle bare stem like spa_centerline
            cand3 = ROOT / "data" / "tracks" / f"{raw}{suffix}"
            if cand3.exists():
                return cand3
    # fallback: assume data/tracks/<raw>
    fallback = ROOT / "data" / "tracks" / raw
    if fallback.exists():
        return fallback
    # last resort: return as-is for error handling
    return p


def scale_track(path: str | pathlib.Path, factor: float) -> pathlib.Path:
    """Deterministically scale a track JSON.

    Scales x, y, s by factor and curv /= factor.
    Writes <stem>_scaled.json in same directory with meta fields.

    Returns the output path (even if dry-run is handled by caller, this
    function always writes).
    """
    src = pathlib.Path(path)
    if not src.is_file():
        raise FileNotFoundError(f"track not found: {src}")
    f = float(factor)
    if not np.isfinite(f) or f <= 0:
        raise ValueError(f"factor must be finite >0, got {factor!r}")

    data = json.loads(src.read_text(encoding="utf-8"))
    points = data.get("points")
    if not isinstance(points, list):
        raise ValueError(f"{src}: missing points list")

    # Use numpy float64 for deterministic multiply/divide (1e-9 contract)
    f64 = np.float64(f)
    inv_f = np.float64(1.0) / f64

    for pt in points:
        # scale x, y, s
        if "x" in pt:
            pt["x"] = float(np.float64(pt["x"]) * f64)
        if "y" in pt:
            pt["y"] = float(np.float64(pt["y"]) * f64)
        if "s" in pt:
            pt["s"] = float(np.float64(pt["s"]) * f64)
        # curv /= f, 0 stays 0
        if "curv" in pt:
            c = float(pt["curv"])
            if c == 0.0:
                pt["curv"] = 0.0
            else:
                pt["curv"] = float(np.float64(c) * inv_f)

    # length_m
    if "length_m" in data:
        data["length_m"] = float(np.float64(data["length_m"]) * f64)

    # meta
    meta = data.get("meta")
    if not isinstance(meta, dict):
        meta = {}
        data["meta"] = meta
    meta["scaled_from"] = src.name
    meta["fia_scaling_factor"] = float(f64)

    # output path: <stem>_scaled.json  (e.g. spa_centerline.json -> spa_centerline_scaled.json)
    # handle .json suffix correctly
    if src.suffix == ".json":
        out_name = src.stem + "_scaled.json"
    else:
        out_name = src.name + "_scaled.json"
    out_path = src.with_name(out_name)

    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def compute_scaled_length(path: str | pathlib.Path, factor: float) -> float:
    """Compute would-be length without writing (for --dry-run)."""
    src = pathlib.Path(path)
    data = json.loads(src.read_text(encoding="utf-8"))
    cur = float(data.get("length_m", 0.0))
    return float(np.float64(cur) * np.float64(factor))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fia_scale.py",
        description="FIA scaling for OpenLAPexe tracks (analysis only, numpy-only, deterministic 1e-9). "
        "Scales x,y,s by factor, curv/=factor, writes <stem>_scaled.json with meta.scaled_from + meta.fia_scaling_factor. "
        "Original file is never mutated. Use --dry-run to preview without writing.",
        epilog="Examples: %(prog)s --dry-run data/tracks/spa_centerline.json 1.007247  -> 7004.00  |  "
        "%(prog)s data/tracks/spa_centerline.json 1.007247  -> writes spa_centerline_scaled.json",
    )
    parser.add_argument("track", nargs="?", help="path to track JSON (e.g. data/tracks/spa_centerline.json)")
    parser.add_argument("factor", nargs="?", help="scaling factor f = L_FIA / L_current (e.g. 1.007247)")
    parser.add_argument("--dry-run", action="store_true", help="print would-be length without writing")
    args = parser.parse_args(argv)

    if args.track is None or args.factor is None:
        parser.print_help(sys.stdout)
        return 2

    track_path = _resolve_track_path(args.track)
    if not track_path.is_file():
        print(f"error: track not found: {args.track} (resolved {track_path})", file=sys.stderr)
        return 1

    try:
        factor = float(args.factor)
    except ValueError:
        print(f"error: factor must be a number, got {args.factor!r}", file=sys.stderr)
        return 1

    if args.dry_run:
        new_len = compute_scaled_length(track_path, factor)
        # print with 2 decimals as required by verification (7004.00)
        print(f"{new_len:.2f}")
        return 0

    out = scale_track(track_path, factor)
    new_len = json.loads(out.read_text(encoding="utf-8")).get("length_m")
    print(f"wrote {out} length_m={float(new_len):.2f} factor={factor} from={track_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
