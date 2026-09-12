#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch SuperGT Suzuka round Q2 bests -> tests/fixtures/supergt_suzuka_q2.json.

Stub: live scrape if reachable else provisional placeholder clearly marked.
- Attempts lightweight HTTP scrape (stdlib only)
- On failure writes provisional placeholder
"""
from __future__ import annotations

import datetime
import json
import pathlib
import sys
import urllib.request
import urllib.error

_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _write_fixture(data: dict, out_path: pathlib.Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _provisional_fixture() -> dict:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return {
        "source": "supergt",
        "event": "SuperGT - Suzuka Round Q2",
        "created": now,
        "provisional": True,
        "note": "provisional placeholder; live scrape not reachable or not implemented",
        "data": {
            "round": "Suzuka",
            "session": "Q2",
            "best_lap_s": None,
            "class": "GT500",
            "provisional": True,
            "info": "placeholder - live SUPER GT official site scrape not available offline",
        },
    }


def _try_live_scrape() -> dict | None:
    """Attempt live scrape of SUPER GT official site (best-effort, no hard dependency).

    Returns dict on success, None on failure.
    """
    urls = [
        "https://supergt.net/en/races/",
        "https://supergt.net/races/",
    ]
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "openlapexe/0.1"})
            with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
                if resp.status != 200:
                    continue
                data = resp.read().decode("utf-8", errors="ignore")
                # Very lightweight check: look for Suzuka + Q2 pattern
                if "Suzuka" in data and ("Q2" in data or "Qualify" in data):
                    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    return {
                        "source": "supergt.net",
                        "event": "SuperGT - Suzuka Round Q2",
                        "created": now,
                        "provisional": False,
                        "url": url,
                        "data": {
                            "round": "Suzuka",
                            "session": "Q2",
                            "best_lap_s": None,
                            "note": "live page reachable but structured Q2 lap parsing not yet implemented; marked provisional lap",
                            "provisional": True,
                        },
                    }
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
            continue
        except Exception:
            continue
    return None


def main() -> None:
    out_path = _ROOT / "tests" / "fixtures" / "supergt_suzuka_q2.json"
    # Try live scrape first
    live = _try_live_scrape()
    if live is not None:
        # Even if page reachable, lap time extraction not implemented -> keep provisional lap but note live reachable
        _write_fixture(live, out_path)
        print(f"saved live-check fixture: {out_path}")
        sys.exit(0)

    # Fallback provisional
    prov = _provisional_fixture()
    _write_fixture(prov, out_path)
    print(f"saved provisional fixture: {out_path}")
    sys.exit(0)


if __name__ == "__main__":
    main()
