#!/usr/bin/env python3
"""Normalize track JSON schema per TDD RED -> GREEN.

(1) Rewrite self-reference meta.source to '*_centerline.json'
    - suzuka keeps overpass origin note: "optimize_centerline min-curvature from suzuka_centerline.json (origin: overpass 68-way)"
(2) Add meta {zone=null with note 'local-frame', schema_version:'2'} to F1 centerlines+racing WITHOUT removing top-level keys
(3) Leave points/lengths/names untouched; atomic tmp.replace writes, utf-8.
"""
from __future__ import annotations

import json
import pathlib

TRACKS_DIR = pathlib.Path(__file__).resolve().parent.parent / "data" / "tracks"
# also support cwd execution fallback
if not TRACKS_DIR.exists():
    TRACKS_DIR = pathlib.Path("data/tracks")


def atomic_write(path: pathlib.Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    # Ensure we use utf-8 and preserve ensure_ascii False, indent 2 to match existing
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def fix_self_reference() -> list[str]:
    touched: list[str] = []
    mapping = {
        "suzuka": "optimize_centerline min-curvature from suzuka_centerline.json (origin: overpass 68-way)",
        "asete": "optimize_centerline min-curvature from asete_centerline.json",
        "test": "optimize_centerline min-curvature from test_centerline.json",
    }
    for stem, good_source in mapping.items():
        p = TRACKS_DIR / f"{stem}.json"
        if not p.exists():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        meta = data.get("meta")
        if not isinstance(meta, dict):
            continue
        cur = meta.get("source") or ""
        bad = f"from {stem}.json"
        good = f"from {stem}_centerline.json"
        # fix if contains bad without good, or exact bad substring
        needs = False
        if bad in cur and good not in cur:
            needs = True
        elif cur != good_source and good in good_source and good not in cur:
            # generic handle: if source is self-ref exact
            if cur == f"optimize_centerline min-curvature from {stem}.json":
                needs = True
        if needs or cur != good_source:
            # Only fix if it's self-ref or not already correct good_source
            # For suzuka/asete/test we force exact good_source
            if cur != good_source:
                # Only rewrite if cur is self-ref or already close; avoid touching unrelated
                if bad in cur or cur == good_source.replace(" (origin: overpass 68-way)", ""):
                    meta["source"] = good_source
                    atomic_write(p, data)
                    touched.append(p.name)
                    print(f"fixed self-ref {p.name}: {cur!r} -> {good_source!r}")
                elif bad in cur:
                    meta["source"] = good_source
                    atomic_write(p, data)
                    touched.append(p.name)
                    print(f"fixed self-ref {p.name}: {cur!r} -> {good_source!r}")
        # Ensure idempotency: if already good, ensure exact
        # Re-read after maybe write to ensure good_source for suzuka etc.
        # Simpler: if cur != good_source and good not in cur and bad in cur -> already handled
        # If cur already good, do nothing
    return touched


def normalize_f1() -> list[str]:
    touched: list[str] = []
    f1_stems = ["spa", "monza", "donington"]
    for stem in f1_stems:
        for suffix in ["", "_centerline"]:
            name = f"{stem}{suffix}.json"
            p = TRACKS_DIR / name
            if not p.exists():
                continue
            data = json.loads(p.read_text(encoding="utf-8"))
            # Do not remove top-level keys - we only touch meta
            meta = data.get("meta")
            if meta is None or not isinstance(meta, dict):
                meta = {}
                data["meta"] = meta
                print(f"create meta for {name}")
            changed = False
            # zone null with note local-frame
            if "zone" not in meta or meta.get("zone") is not None:
                # spa/monza/donington are local coords => null
                if meta.get("zone") is not None:
                    print(f"{name}: zone {meta.get('zone')!r} -> None (local-frame)")
                meta["zone"] = None
                changed = True
            elif "zone" not in meta:
                meta["zone"] = None
                changed = True
            # note local-frame : ensure some field documents local-frame
            # Use 'note' if absent, else 'zone_note'
            has_local = False
            for k, v in list(meta.items()):
                if isinstance(v, str) and "local-frame" in v:
                    has_local = True
                    break
            if not has_local:
                # Prefer 'note' key, keep backward compat
                if "note" not in meta:
                    meta["note"] = "local-frame"
                elif "local-frame" not in str(meta["note"]):
                    meta["note"] = str(meta["note"]) + " local-frame"
                else:
                    pass
                changed = True
                # Also add explicit zone_note for clarity
                if "zone_note" not in meta:
                    meta["zone_note"] = "local-frame"
                    changed = True
            # schema_version '2' as string
            if meta.get("schema_version") != "2":
                meta["schema_version"] = "2"
                changed = True
            if changed:
                # Leave points/lengths/names untouched - we only modified meta
                atomic_write(p, data)
                touched.append(name)
                print(f"normalized F1 {name}: zone=null note=local-frame schema_version=2")
    return touched


def remove_duplicate() -> list[str]:
    touched: list[str] = []
    dup = TRACKS_DIR / "suzuka_south (コース中心線).json"
    if dup.exists():
        dup.unlink()
        touched.append(dup.name)
        print(f"removed duplicate {dup.name}")
    else:
        print(f"duplicate not present (skipped): {dup.name}")
    return touched


def main() -> None:
    print(f"TRACKS_DIR={TRACKS_DIR.resolve()}")
    a = fix_self_reference()
    b = normalize_f1()
    c = remove_duplicate()
    print(f"done: self_ref_fixed={a} f1_normalized={b} removed={c}")


if __name__ == "__main__":
    main()
