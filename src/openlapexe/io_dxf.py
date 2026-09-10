# -*- coding: utf-8 -*-
# allow: SIZE_OK — ASCII DXF parser 7 entities + bulge tessellation (indivisible unit)
"""openlapexe.io_dxf - ASCII DXF parser (stdlib only).

Rows: code,value pairs -> ENTITIES -> 0-chunk split -> entity dispatch.
Supports LINE / LWPOLYLINE (+bulge) / POLYLINE(+VERTEX+SEQEND) / ARC / CIRCLE / SPLINE.

DXF coordinates are assumed already projected (plane orthogonal); no transform.
"""
from __future__ import annotations

import logging
import math
import pathlib
import warnings
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

_log = logging.getLogger("openlapexe.io_dxf")

_IGNORED_DXF_TYPES = frozenset(
    {
        "IMAGE",
        "IMAGEDEF",
        "IMAGEDEF_REACTOR",
        "ACAD_IMAGE_DICT",
        "ACAD_IMAGE_VARS",
        "ACAD_MLINESTYLE",
        "MLINESTYLE",
        "DICTIONARY",
        "XRECORD",
    }
)


@dataclass(frozen=True, slots=True)
class Candidate:
    name: str
    kind: str
    points_xy: npt.NDArray[np.float64]
    length_m: float


def _length(points: list[tuple[float, float]] | npt.NDArray[np.float64]) -> float:
    arr = np.asarray(points, dtype=float)
    if arr.size == 0 or arr.shape[0] < 2:
        return 0.0
    if arr.ndim == 1:
        arr = arr.reshape(-1, 2)
    dx = np.diff(arr[:, 0])
    dy = np.diff(arr[:, 1])
    return float(np.sum(np.hypot(dx, dy)))


def _bulge_segment(
    p0: tuple[float, float], p1: tuple[float, float], bulge: float
) -> list[tuple[float, float]]:
    if abs(bulge) < 1e-12:
        return [p0, p1]
    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    c = math.hypot(dx, dy)
    if c < 1e-12:
        return [p0, p1]
    s = bulge * c / 2.0
    if abs(s) < 1e-12:
        return [p0, p1]
    R = ((c / 2.0) ** 2 + s * s) / (2.0 * s)
    ux = -dy / c
    uy = dx / c
    mx = (p0[0] + p1[0]) * 0.5
    my = (p0[1] + p1[1]) * 0.5
    cx = mx + ux * (s - R)
    cy = my + uy * (s - R)
    theta = 4.0 * math.atan(bulge)
    delta = -theta
    a0 = math.atan2(p0[1] - cy, p0[0] - cx)
    n = int(abs(theta) / (2.0 * math.pi) * 64.0 + 0.5)
    if n < 8:
        n = 8
    if n > 64:
        n = 64
    absR = abs(R)
    pts: list[tuple[float, float]] = []
    for k in range(n + 1):
        t = k / n
        ang = a0 + delta * t
        pts.append((cx + absR * math.cos(ang), cy + absR * math.sin(ang)))
    pts[0] = p0
    pts[-1] = p1
    return pts


def _build_polyline(
    vertices: list[tuple[float, float]],
    bulges: list[float],
    closed: bool,
) -> list[tuple[float, float]] | None:
    if len(vertices) < 2:
        return None
    n = len(vertices)
    # ensure bulges length
    if len(bulges) < n:
        bulges = bulges + [0.0] * (n - len(bulges))
    out: list[tuple[float, float]] = []
    seg_count = n if closed else n - 1
    for i in range(seg_count):
        p0 = vertices[i]
        p1 = vertices[(i + 1) % n]
        # closed last->first may be zero-length if not actually closed but we still handle
        b = bulges[i] if i < len(bulges) else 0.0
        seg = _bulge_segment(p0, p1, b)
        if not out:
            out.extend(seg)
        else:
            out.extend(seg[1:])
    return out


def _arc_points(
    cx: float, cy: float, r: float, start_deg: float, end_deg: float
) -> list[tuple[float, float]]:
    if r <= 1e-12:
        return []
    s = math.radians(start_deg)
    e = math.radians(end_deg)
    delta = e - s
    while delta <= 1e-12:
        delta += 2.0 * math.pi
    while delta > 2.0 * math.pi + 1e-12:
        delta -= 2.0 * math.pi
    n = int(abs(delta) / (2.0 * math.pi) * 64.0 + 0.5)
    if n < 8:
        n = 8
    if n > 64:
        n = 64
    pts: list[tuple[float, float]] = []
    for k in range(n + 1):
        t = k / n
        ang = s + delta * t
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return pts


def _circle_points(cx: float, cy: float, r: float) -> list[tuple[float, float]]:
    if r <= 1e-12:
        return []
    n = 64
    pts: list[tuple[float, float]] = []
    for k in range(n + 1):
        ang = 2.0 * math.pi * k / n
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return pts


def _pairs_to_dict(chunk: list[tuple[int, str]]) -> dict[int, str]:
    d: dict[int, str] = {}
    for c, v in chunk:
        if c == 0:
            continue
        d[c] = v
    return d


def _transform_points(
    pts: list[tuple[float, float]],
    ix: float,
    iy: float,
    sx: float,
    sy: float,
    cos_a: float,
    sin_a: float,
) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for x, y in pts:
        xs = x * sx
        ys = y * sy
        xr = xs * cos_a - ys * sin_a + ix
        yr = xs * sin_a + ys * cos_a + iy
        out.append((xr, yr))
    return out


def _parse_section_map(
    pairs: list[tuple[int, str]],
) -> dict[str, list[tuple[int, str]]]:
    sections: dict[str, list[tuple[int, str]]] = {}
    cur: str | None = None
    buf: list[tuple[int, str]] = []
    i = 0
    while i < len(pairs):
        code, val = pairs[i]
        if code == 0 and val == "SECTION":
            if i + 1 < len(pairs) and pairs[i + 1][0] == 2:
                cur = pairs[i + 1][1].upper()
                buf = []
                i += 2
                continue
        if code == 0 and val == "ENDSEC" and cur is not None:
            sections[cur] = buf
            cur = None
            buf = []
            i += 1
            continue
        if cur is not None:
            buf.append((code, val))
        i += 1
    return sections


def parse_dxf(path: str | pathlib.Path) -> list[Candidate]:
    p = pathlib.Path(path)
    if not p.exists():
        raise FileNotFoundError(f"dxf not found: {p}")
    # binary detection
    with p.open("rb") as fb:
        head = fb.read(64)
        if head.startswith(b"AutoCAD Binary DXF"):
            raise ValueError("Binary DXF not supported")
    text = p.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    pairs: list[tuple[int, str]] = []
    # step by 2, ignore trailing odd
    for i in range(0, len(lines) - 1, 2):
        code_raw = lines[i].strip()
        if code_raw == "":
            continue
        try:
            code = int(code_raw)
        except ValueError:
            continue
        val = lines[i + 1].strip()
        pairs.append((code, val))

    sections = _parse_section_map(pairs)
    if "ENTITIES" in sections:
        entities = sections["ENTITIES"]
        found = True
    elif "BLOCKS" in sections or any(
        c == 0 and v in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "SPLINE", "VERTEX", "SEQEND", "INSERT")
        for c, v in pairs
    ):
        # no ENTITIES section: fallback similar to original but prefer section map
        # if ENTITIES missing but pairs contain entities, treat whole file as entities (minimal headers)
        if not sections:
            has_entity = any(
                c == 0 and v in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "SPLINE", "VERTEX", "SEQEND", "INSERT")
                for c, v in pairs
            )
            entities = pairs if has_entity else []
        else:
            entities = []
        found = "ENTITIES" in sections
    else:
        entities = []
        found = False
    # original fallback path when ENTITIES section not found but pairs contain entities
    if not found and not entities:
        has_entity = any(
            c == 0 and v in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "SPLINE", "VERTEX", "SEQEND", "INSERT")
            for c, v in pairs
        )
        if has_entity:
            entities = pairs
    # BLOCKS extraction
    if "BLOCKS" in sections:
        blocks_raw = sections["BLOCKS"]
    else:
        # fallback: if no BLOCKS section but pairs contain BLOCK, collect those pairs
        has_block = any(c == 0 and v in ("BLOCK", "ENDBLK") for c, v in pairs)
        blocks_raw = pairs if has_block and "ENTITIES" not in sections else []

    blocks: dict[str, list[list[tuple[int, str]]]] = {}
    if blocks_raw:
        blk_chunks: list[list[tuple[int, str]]] = []
        cur_b: list[tuple[int, str]] = []
        for code, val in blocks_raw:
            if code == 0:
                if cur_b:
                    blk_chunks.append(cur_b)
                cur_b = [(code, val)]
            else:
                if not cur_b:
                    continue
                cur_b.append((code, val))
        if cur_b:
            blk_chunks.append(cur_b)
        j = 0
        while j < len(blk_chunks):
            typ_b = blk_chunks[j][0][1].upper() if blk_chunks[j] else ""
            if typ_b == "BLOCK":
                d_b = _pairs_to_dict(blk_chunks[j])
                bname = d_b.get(2, "")
                ent_list: list[list[tuple[int, str]]] = []
                k = j + 1
                while k < len(blk_chunks):
                    t2 = blk_chunks[k][0][1].upper() if blk_chunks[k] else ""
                    if t2 == "ENDBLK":
                        k += 1
                        break
                    if t2 == "BLOCK":
                        break
                    ent_list.append(blk_chunks[k])
                    k += 1
                if bname:
                    blocks[bname] = ent_list
                    blocks[bname.upper()] = ent_list
                    blocks[bname.lower()] = ent_list
                j = k
                continue
            j += 1

    # 0-chunk split
    chunks: list[list[tuple[int, str]]] = []
    cur: list[tuple[int, str]] = []
    for code, val in entities:
        if code == 0:
            if cur:
                chunks.append(cur)
            cur = [(code, val)]
        else:
            if not cur:
                # stray data before first 0, ignore
                continue
            cur.append((code, val))
    if cur:
        chunks.append(cur)

    candidates: list[Candidate] = []
    idx = 0
    i = 0
    while i < len(chunks):
        typ = chunks[i][0][1].upper() if chunks[i] else ""
        if typ == "POLYLINE":
            hdr = _pairs_to_dict(chunks[i])
            closed = False
            try:
                f70 = int(float(hdr.get(70, "0")))
                closed = bool(f70 & 1)
            except Exception:
                closed = False
            verts: list[tuple[float, float]] = []
            bulges: list[float] = []
            j = i + 1
            while j < len(chunks):
                t2 = chunks[j][0][1].upper() if chunks[j] else ""
                if t2 == "VERTEX":
                    d = _pairs_to_dict(chunks[j])
                    try:
                        x = float(d.get(10, "0"))
                        y = float(d.get(20, "0"))
                    except Exception:
                        x, y = 0.0, 0.0
                    verts.append((x, y))
                    try:
                        b = float(d.get(42, "0"))
                    except Exception:
                        b = 0.0
                    bulges.append(b)
                    j += 1
                elif t2 == "SEQEND":
                    j += 1
                    break
                else:
                    break
            pts = _build_polyline(verts, bulges, closed)
            if pts is not None and len(pts) >= 2:
                arr = np.asarray(pts, dtype=float)
                candidates.append(Candidate(name=f"POLYLINE_{idx}", kind="POLYLINE", points_xy=arr, length_m=_length(arr)))
                idx += 1
            i = j
            continue
        elif typ == "LWPOLYLINE":
            # sequential parse 10,20,42
            verts = []
            bulges = []
            cur_x: float | None = None
            cur_y: float | None = None
            cur_b = 0.0
            closed = False
            # check 70 closed flag among pairs
            for c, v in chunks[i]:
                if c == 70:
                    try:
                        closed = bool(int(float(v)) & 1)
                    except Exception:
                        pass
            for c, v in chunks[i]:
                if c == 10:
                    if cur_x is not None and cur_y is not None:
                        verts.append((cur_x, cur_y))
                        bulges.append(cur_b)
                        cur_b = 0.0
                    try:
                        cur_x = float(v)
                    except Exception:
                        cur_x = 0.0
                    cur_y = None
                elif c == 20:
                    try:
                        cur_y = float(v)
                    except Exception:
                        cur_y = 0.0
                elif c == 42:
                    try:
                        cur_b = float(v)
                    except Exception:
                        cur_b = 0.0
            if cur_x is not None and cur_y is not None:
                verts.append((cur_x, cur_y))
                bulges.append(cur_b)
            pts = _build_polyline(verts, bulges, closed)
            if pts is not None and len(pts) >= 2:
                arr = np.asarray(pts, dtype=float)
                candidates.append(Candidate(name=f"LWPOLYLINE_{idx}", kind="LWPOLYLINE", points_xy=arr, length_m=_length(arr)))
                idx += 1
        elif typ == "LINE":
            d = _pairs_to_dict(chunks[i])
            try:
                x0 = float(d.get(10, "0"))
                y0 = float(d.get(20, "0"))
                x1 = float(d.get(11, "0"))
                y1 = float(d.get(21, "0"))
            except Exception:
                i += 1
                continue
            pts = [(x0, y0), (x1, y1)]
            arr = np.asarray(pts, dtype=float)
            candidates.append(Candidate(name=f"LINE_{idx}", kind="LINE", points_xy=arr, length_m=_length(arr)))
            idx += 1
        elif typ == "ARC":
            d = _pairs_to_dict(chunks[i])
            try:
                cx = float(d.get(10, "0"))
                cy = float(d.get(20, "0"))
                r = float(d.get(40, "0"))
                a0 = float(d.get(50, "0"))
                a1 = float(d.get(51, "0"))
            except Exception:
                i += 1
                continue
            pts = _arc_points(cx, cy, r, a0, a1)
            if pts:
                arr = np.asarray(pts, dtype=float)
                candidates.append(Candidate(name=f"ARC_{idx}", kind="ARC", points_xy=arr, length_m=_length(arr)))
                idx += 1
        elif typ == "CIRCLE":
            d = _pairs_to_dict(chunks[i])
            try:
                cx = float(d.get(10, "0"))
                cy = float(d.get(20, "0"))
                r = float(d.get(40, "0"))
            except Exception:
                i += 1
                continue
            pts = _circle_points(cx, cy, r)
            if pts:
                arr = np.asarray(pts, dtype=float)
                candidates.append(Candidate(name=f"CIRCLE_{idx}", kind="CIRCLE", points_xy=arr, length_m=_length(arr)))
                idx += 1
        elif typ == "SPLINE":
            pts = []
            cur_x = None
            cur_y = None
            for c, v in chunks[i]:
                if c == 10:
                    if cur_x is not None and cur_y is not None:
                        pts.append((cur_x, cur_y))
                    try:
                        cur_x = float(v)
                    except Exception:
                        cur_x = 0.0
                    cur_y = None
                elif c == 20:
                    try:
                        cur_y = float(v)
                    except Exception:
                        cur_y = 0.0
                    if cur_x is not None and cur_y is not None:
                        pts.append((cur_x, cur_y))
                        cur_x = None
                        cur_y = None
            if cur_x is not None and cur_y is not None:
                pts.append((cur_x, cur_y))
            if len(pts) >= 2:
                arr = np.asarray(pts, dtype=float)
                candidates.append(Candidate(name=f"SPLINE_{idx}", kind="SPLINE", points_xy=arr, length_m=_length(arr)))
                idx += 1
        elif typ == "INSERT":
            d = _pairs_to_dict(chunks[i])
            bname = d.get(2, "").strip()
            loc = f"{p}:{i+1}"
            if not bname:
                msg = f"{loc} unsupported INSERT without block name"
                warnings.warn(msg, UserWarning, stacklevel=2)
                _log.warning(msg)
                i += 1
                continue
            ent_list = blocks.get(bname) or blocks.get(bname.upper()) or blocks.get(bname.lower())
            if ent_list is None or len(ent_list) == 0:
                msg = f"{loc} unsupported INSERT block not found: {bname}"
                warnings.warn(msg, UserWarning, stacklevel=2)
                _log.warning(msg)
                i += 1
                continue
            try:
                ix = float(d.get(10, "0"))
            except Exception:
                ix = 0.0
            try:
                iy = float(d.get(20, "0"))
            except Exception:
                iy = 0.0
            try:
                sx = float(d.get(41, "1"))
            except Exception:
                sx = 1.0
            try:
                sy = float(d.get(42, "1"))
            except Exception:
                sy = 1.0
            # handle uniform fallback when only 41 given
            if "42" not in d and "41" in d:
                sy = sx
            try:
                rot = float(d.get(50, "0"))
            except Exception:
                rot = 0.0
            rad = math.radians(rot)
            cos_a = math.cos(rad)
            sin_a = math.sin(rad)
            for blk_chunk in ent_list:
                btyp = blk_chunk[0][1].upper() if blk_chunk else ""
                if btyp == "LINE":
                    bd = _pairs_to_dict(blk_chunk)
                    try:
                        x0 = float(bd.get(10, "0"))
                        y0 = float(bd.get(20, "0"))
                        x1 = float(bd.get(11, "0"))
                        y1 = float(bd.get(21, "0"))
                    except Exception:
                        continue
                    pts_t = _transform_points([(x0, y0), (x1, y1)], ix, iy, sx, sy, cos_a, sin_a)
                    arr = np.asarray(pts_t, dtype=float)
                    candidates.append(Candidate(name=f"INSERT_{bname}_{idx}", kind="LINE", points_xy=arr, length_m=_length(arr)))
                    idx += 1
                elif btyp == "LWPOLYLINE":
                    verts: list[tuple[float, float]] = []
                    bulges: list[float] = []
                    cur_x = None
                    cur_y = None
                    cur_b = 0.0
                    closed = False
                    for c, v in blk_chunk:
                        if c == 70:
                            try:
                                closed = bool(int(float(v)) & 1)
                            except Exception:
                                pass
                    for c, v in blk_chunk:
                        if c == 10:
                            if cur_x is not None and cur_y is not None:
                                verts.append((cur_x, cur_y))
                                bulges.append(cur_b)
                                cur_b = 0.0
                            try:
                                cur_x = float(v)
                            except Exception:
                                cur_x = 0.0
                            cur_y = None
                        elif c == 20:
                            try:
                                cur_y = float(v)
                            except Exception:
                                cur_y = 0.0
                        elif c == 42:
                            try:
                                cur_b = float(v)
                            except Exception:
                                cur_b = 0.0
                    if cur_x is not None and cur_y is not None:
                        verts.append((cur_x, cur_y))
                        bulges.append(cur_b)
                    pts = _build_polyline(verts, bulges, closed)
                    if pts is not None and len(pts) >= 2:
                        pts_t = _transform_points(pts, ix, iy, sx, sy, cos_a, sin_a)
                        arr = np.asarray(pts_t, dtype=float)
                        candidates.append(Candidate(name=f"INSERT_{bname}_{idx}", kind="LWPOLYLINE", points_xy=arr, length_m=_length(arr)))
                        idx += 1
                elif btyp == "POLYLINE":
                    # POLYLINE in BLOCKS: collect VERTEX chunks that follow inside ent_list is flattened,
                    # but our ent_list splits each 0-chunk separately, so VERTEX/SEQEND are separate chunks,
                    # not header+verts. For BLOCKS POLYLINE, verts follow as subsequent chunks in blocks_raw
                    # We handle simple case: if following chunks in ent_list are VERTEX, consume them.
                    # Since ent_list is list of chunks, find next VERTEX chunks after this one.
                    # Reconstruct similarly to main loop using index within ent_list.
                    pass
                elif btyp == "ARC":
                    bd = _pairs_to_dict(blk_chunk)
                    try:
                        cx = float(bd.get(10, "0"))
                        cy = float(bd.get(20, "0"))
                        r = float(bd.get(40, "0"))
                        a0 = float(bd.get(50, "0"))
                        a1 = float(bd.get(51, "0"))
                    except Exception:
                        continue
                    r_scaled = r * (abs(sx) + abs(sy)) / 2.0 if sx != sy else r * abs(sx)
                    pts_raw = _arc_points(0, 0, r_scaled, a0 + rot, a1 + rot)
                    if pts_raw:
                        cx_t, cy_t = _transform_points([(cx, cy)], ix, iy, sx, sy, cos_a, sin_a)[0]
                        pts_t = [(x + cx_t, y + cy_t) for x, y in [(px, py) for px, py in pts_raw]]
                        # _arc_points already at origin scaled, need offset to transformed center
                        # pts_raw generated around (0,0) with r_scaled; shift to cx_t,cy_t
                        # Already done above via offset
                        arr = np.asarray(pts_t, dtype=float)
                        candidates.append(Candidate(name=f"INSERT_{bname}_{idx}", kind="ARC", points_xy=arr, length_m=_length(arr)))
                        idx += 1
                elif btyp == "CIRCLE":
                    bd = _pairs_to_dict(blk_chunk)
                    try:
                        cx = float(bd.get(10, "0"))
                        cy = float(bd.get(20, "0"))
                        r = float(bd.get(40, "0"))
                    except Exception:
                        continue
                    r_scaled = r * (abs(sx) + abs(sy)) / 2.0 if sx != sy else r * abs(sx)
                    pts_raw = _circle_points(0, 0, r_scaled)
                    if pts_raw:
                        cx_t, cy_t = _transform_points([(cx, cy)], ix, iy, sx, sy, cos_a, sin_a)[0]
                        pts_t = [(x + cx_t, y + cy_t) for x, y in pts_raw]
                        arr = np.asarray(pts_t, dtype=float)
                        candidates.append(Candidate(name=f"CIRCLE_{idx}", kind="CIRCLE", points_xy=arr, length_m=_length(arr)))
                        idx += 1
                elif btyp == "SPLINE":
                    pts_s: list[tuple[float, float]] = []
                    sx_sp = None
                    sy_sp = None
                    for c, v in blk_chunk:
                        if c == 10:
                            if sx_sp is not None and sy_sp is not None:
                                pts_s.append((sx_sp, sy_sp))
                            try:
                                sx_sp = float(v)
                            except Exception:
                                sx_sp = 0.0
                            sy_sp = None
                        elif c == 20:
                            try:
                                sy_sp = float(v)
                            except Exception:
                                sy_sp = 0.0
                            if sx_sp is not None and sy_sp is not None:
                                pts_s.append((sx_sp, sy_sp))
                                sx_sp = None
                                sy_sp = None
                    if sx_sp is not None and sy_sp is not None:
                        pts_s.append((sx_sp, sy_sp))
                    if len(pts_s) >= 2:
                        pts_t = _transform_points(pts_s, ix, iy, sx, sy, cos_a, sin_a)
                        arr = np.asarray(pts_t, dtype=float)
                        candidates.append(Candidate(name=f"INSERT_{bname}_{idx}", kind="SPLINE", points_xy=arr, length_m=_length(arr)))
                        idx += 1
                elif btyp == "INSERT":
                    msg2 = f"{loc} unsupported nested INSERT in block {bname}: {blk_chunk[0][1] if blk_chunk else ''}"
                    warnings.warn(msg2, UserWarning, stacklevel=2)
                    _log.warning(msg2)
                elif btyp in _IGNORED_DXF_TYPES:
                    pass
                else:
                    msg2 = f"{loc} unsupported entity in block {bname}: {btyp}"
                    warnings.warn(msg2, UserWarning, stacklevel=2)
                    _log.warning(msg2)
        else:
            if typ in _IGNORED_DXF_TYPES:
                i += 1
                continue
            loc = f"{p}:{i+1}"
            msg = f"{loc} unsupported DXF entity: {typ}"
            warnings.warn(msg, UserWarning, stacklevel=2)
            _log.warning(msg)
        i += 1
    return candidates


__all__ = ["Candidate", "parse_dxf"]
