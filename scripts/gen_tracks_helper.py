#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_tracks_helper - deterministic KML -> Track JSON helper (numpy-only).

Provides:
  kml_to_track(kml_path, zone, out_name, closed_loop=True)
    parse_kml -> wgs84_to_plane per point -> Track.from_candidates(mode='kml') -> save_json

Constraints: stdlib + existing package only (numpy, openlapexe). Deterministic.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

# Ensure src on path when run as script
_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import numpy as np  # noqa: E402

from openlapexe.geo_proj import wgs84_to_plane  # noqa: E402
from openlapexe.io_kml import parse_kml  # noqa: E402
from openlapexe.track import Track  # noqa: E402


def kml_to_track(
    kml_path: str | pathlib.Path,
    zone: int | None,
    out_name: str,
    closed_loop: bool = True,
) -> pathlib.Path:
    """Parse KML and produce Track JSON.

    Args:
        kml_path: path to .kml file
        zone: plane zone number (int) or None for auto
        out_name: track json name (without .json ok)
        closed_loop: whether track is closed loop

    Returns:
        Path to saved json file.

    Pipeline:
        parse_kml(kml_path) -> per-point wgs84_to_plane(lat,lon,zone) -> Track.from_candidates(mode='kml') -> save_json
    """
    kml_path = pathlib.Path(kml_path)
    if not kml_path.exists():
        raise FileNotFoundError(f"kml not found: {kml_path}")
    cands = parse_kml(kml_path)
    if not cands:
        raise ValueError(f"no candidates in kml: {kml_path}")
    # Prefer longest candidate (deterministic: sort by length desc, then name)
    cands_sorted = sorted(cands, key=lambda c: (-float(c.length_m), str(c.name)))
    chosen = cands_sorted[0]

    pts = chosen.points_lonlat
    if not pts:
        raise ValueError(f"chosen candidate has no points: {chosen.name}")

    # wgs84_to_plane per point (vectorized for determinism)
    lons = np.array([float(p[0]) for p in pts], dtype=float)
    lats = np.array([float(p[1]) for p in pts], dtype=float)

    # Resolve zone: explicit int -> use; None -> auto via wgs84_to_plane
    if zone is not None:
        zone_int = int(zone)
        x_arr, y_arr, zone_arr = wgs84_to_plane(lats, lons, zone_int)
    else:
        x_arr, y_arr, zone_arr = wgs84_to_plane(lats, lons)

    x_arr = np.asarray(x_arr, dtype=float).reshape(-1)
    y_arr = np.asarray(y_arr, dtype=float).reshape(-1)

    # Determine zone value for meta
    if isinstance(zone_arr, np.ndarray):
        try:
            zone_val = int(zone_arr.flat[0])
        except Exception:
            zone_val = int(zone) if zone is not None else None
    else:
        try:
            zone_val = int(zone_arr)
        except Exception:
            zone_val = int(zone) if zone is not None else None

    points_xy = np.column_stack([x_arr, y_arr])

    # Build candidate dict for Track.from_candidates
    cand_dict = {
        "name": str(out_name).strip() or chosen.name or "kml_track",
        "points_xy": points_xy,
    }

    track = Track.from_candidates([cand_dict], mode="kml", closed_loop=bool(closed_loop))
    # Ensure meta zone is set
    try:
        track.meta["zone"] = zone_val
    except Exception:
        pass
    # Override name to out_name
    track.name = str(out_name).strip() or track.name

    out_path = track.save_json(str(out_name).strip())
    return out_path


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gen_tracks_helper",
        description="KML -> Track JSON helper (deterministic, numpy-only)",
    )
    p.add_argument("kml_path", nargs="?", help="path to input .kml file")
    p.add_argument("--zone", type=int, default=None, help="plane zone (1..19 JP or UTM 20..60, auto if omitted)")
    p.add_argument("--out", type=str, default=None, help="output track name (without .json)")
    p.add_argument("--closed-loop", dest="closed_loop", action="store_true", default=True, help="closed loop (default: true)")
    p.add_argument("--no-closed-loop", dest="closed_loop", action="store_false", help="open track")
    p.add_argument("--out-name", type=str, default=None, help="alias for --out")
    return p


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    # --help handled by argparse (exit 0)
    if args.kml_path is None:
        # No positional -> show help and exit 0 if --help not given? We treat as help case.
        # If invoked with no args, also show help (exit 0 to satisfy --help must exit 0 contract when help shown)
        parser.print_help()
        sys.exit(0)
    # Resolve out_name
    out_name = args.out if args.out is not None else args.out_name
    if out_name is None:
        # derive from kml filename
        out_name = pathlib.Path(args.kml_path).stem
    kml_to_track(args.kml_path, args.zone, out_name, closed_loop=bool(args.closed_loop))
    print(f"saved: {out_name}.json")


if __name__ == "__main__":
    main()
