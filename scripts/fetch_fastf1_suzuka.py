#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch FastF1 Suzuka Q fastest laps (2024/2025 Japan GP) -> tests/fixtures/fastf1_suzuka_q.json.

- Import fastf1 inside try (isolated, no hard dep)
- Cache to /tmp/fastf1
- Fetch 2024 Japan Q fastest + 2025 Japan Q fastest
- On network failure write fixture with known values 88.197/86.983 marked provisional
"""
from __future__ import annotations

import datetime
import json
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _write_fixture(data: dict, out_path: pathlib.Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _provisional_fixture() -> dict:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return {
        "source": "fastf1",
        "event": "Japan GP - Suzuka Qualifying",
        "created": now,
        "provisional": True,
        "note": "network unavailable or fastf1 not installed; provisional placeholder with known reference values",
        "years": {
            "2024": {
                "session": "Q",
                "fastest_lap_s": 88.197,
                "driver": "VER",
                "provisional": True,
            },
            "2025": {
                "session": "Q",
                "fastest_lap_s": 86.983,
                "driver": "VER",
                "provisional": True,
            },
        },
    }


def main() -> None:
    out_path = _ROOT / "tests" / "fixtures" / "fastf1_suzuka_q.json"
    # provisional fallback data (known values from spec)
    fallback = _provisional_fixture()

    try:
        import fastf1  # type: ignore

        cache_dir = pathlib.Path("/tmp/fastf1")
        cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            fastf1.Cache.enable_cache(str(cache_dir))  # type: ignore[attr-defined]
        except Exception:
            pass

        result: dict = {
            "source": "fastf1",
            "event": "Japan GP - Suzuka Qualifying",
            "created": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "provisional": False,
            "years": {},
        }

        success_any = False
        for year in (2024, 2025):
            try:
                session = fastf1.get_session(year, "Japan", "Q")  # type: ignore[attr-defined]
                session.load(telemetry=False, weather=False)  # type: ignore[attr-defined]
                # fastest lap
                laps = session.laps  # type: ignore[attr-defined]
                # pick fastest overall
                fastest = laps.pick_fastest()  # type: ignore[attr-defined]
                lap_time = fastest["LapTime"]  # timedelta
                # convert to seconds
                try:
                    lap_s = float(lap_time.total_seconds())
                except Exception:
                    lap_s = float(fallback["years"][str(year)]["fastest_lap_s"])
                driver = ""
                try:
                    driver = str(fastest["Driver"])
                except Exception:
                    driver = ""
                if not driver:
                    try:
                        driver = str(fastest["DriverNumber"])
                    except Exception:
                        driver = ""
                if not driver:
                    driver = fallback["years"][str(year)].get("driver", "")
                result["years"][str(year)] = {
                    "session": "Q",
                    "fastest_lap_s": round(float(lap_s), 3),
                    "driver": driver,
                    "provisional": False,
                }
                success_any = True
            except Exception as e:
                # per-year failure -> use provisional for that year
                prov = fallback["years"][str(year)]
                result["years"][str(year)] = dict(prov)
                result["years"][str(year)]["error"] = str(e)[:500]

        # If none succeeded, mark provisional overall
        if not success_any:
            result["provisional"] = True
            result["note"] = "all years failed; values are provisional placeholders 88.197/86.983"
            # ensure values are correct fallback
            for y in ("2024", "2025"):
                if y not in result["years"]:
                    result["years"][y] = dict(fallback["years"][y])

        # Validate provisional fallback values still present if failed
        for y in ("2024", "2025"):
            if "fastest_lap_s" not in result["years"][y]:
                result["years"][y]["fastest_lap_s"] = float(fallback["years"][y]["fastest_lap_s"])

        _write_fixture(result, out_path)
        print(f"saved: {out_path} provisional={result.get('provisional', False)}")
        sys.exit(0)

    except ImportError as e:
        # fastf1 not installed
        fallback["import_error"] = f"fastf1 not installed: {e}"
        _write_fixture(fallback, out_path)
        print(f"fastf1 not installed, wrote provisional fixture: {out_path}", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        # network fail or other
        fallback["error"] = str(e)[:800]
        _write_fixture(fallback, out_path)
        print(f"fetch failed ({e}), wrote provisional fixture: {out_path}", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
