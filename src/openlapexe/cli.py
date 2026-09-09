# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import pathlib
import sys


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="openlapexe",
        description="OpenLAPexe headless CLI (GUI default when no flags)",
        add_help=True,
    )
    p.add_argument("--headless", action="store_true", help="GUIなしで実行 (headless mode)")
    p.add_argument("--vehicle", type=str, default="f1", help="車両名/パス (例: f1, gt)")
    p.add_argument("--track", type=str, default="spa", help="コース名/パス (例: spa, monza)")
    p.add_argument("--validate", type=str, metavar="PATH", help="JSONを検証 (車両/トラック) パスを指定")
    p.add_argument("--dry-run", dest="dry_run", action="store_true", help="ファイルを作成せずに検証/計算のみ")
    p.add_argument("--json", dest="as_json", action="store_true", help="結果をJSONでstdoutに出力")
    p.add_argument("--output", type=str, default=None, help="出力先パス (省略時はstdoutのみ)")
    p.add_argument("--freq", type=int, default=50, help="エクスポート周波数 1..200 (既定 50)")
    return p


def _handle_validate(path_str: str, as_json: bool) -> None:
    if not path_str or not path_str.strip():
        print(f"エラー: パスが無効です: {path_str!r}", file=sys.stderr)
        print("ヒント: --validate に有効なファイルパスを指定してください (--help 参照)", file=sys.stderr)
        sys.exit(2)
    path = pathlib.Path(path_str)
    if not path.exists():
        print(f"エラー: パスが見つかりません: {path_str}", file=sys.stderr)
        print("ヒント: ファイルが存在するか確認してください (--help 参照)", file=sys.stderr)
        sys.exit(2)
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"エラー: JSONの解析に失敗しました パス: {path_str} 詳細: {e}", file=sys.stderr)
        print("ヒント: UTF-8の有効なJSONであることを確認してください", file=sys.stderr)
        sys.exit(2)
    except OSError as e:
        print(f"エラー: ファイル読み込み失敗 パス: {path_str} 詳細: {e}", file=sys.stderr)
        print("ヒント: パスと権限を確認してください", file=sys.stderr)
        sys.exit(2)
    try:
        from openlapexe.io import validate_track_dict, validate_vehicle_dict
    except Exception as e:
        print(f"エラー: バリデータ読み込み失敗: {e}", file=sys.stderr)
        sys.exit(1)
    ok = False
    kind = ""
    err_v: Exception | None = None
    err_t: Exception | None = None
    try:
        validate_vehicle_dict(data)
        ok = True
        kind = "vehicle"
    except Exception as e:
        err_v = e
    if not ok:
        try:
            validate_track_dict(data)
            ok = True
            kind = "track"
        except Exception as e:
            err_t = e
    if not ok:
        detail = str(err_v) if err_v is not None else str(err_t)
        print(f"エラー: 検証失敗 パス: {path_str} 詳細: {detail}", file=sys.stderr)
        print("ヒント: 必須キーを確認してください (vehicle: mass_kg等 / track: points等) --help 参照", file=sys.stderr)
        sys.exit(2)
    if as_json:
        print(json.dumps({"status": "ok", "path": path_str, "kind": kind}, ensure_ascii=False))
    else:
        print(f"OK: {path_str} ({kind}) valid")
    sys.exit(0)


def _handle_headless(args: argparse.Namespace) -> None:
    try:
        from openlapexe.solver import simulate_full
    except Exception as e:
        print(f"エラー: ソルバー読み込み失敗: {e}", file=sys.stderr)
        print("ヒント: パッケージのインストールを確認してください", file=sys.stderr)
        sys.exit(1)
    vehicle = args.vehicle
    track = args.track
    freq = args.freq
    try:
        result = simulate_full(vehicle, track, freq=freq)
    except TypeError as e:
        print(f"エラー: 引数が無効です パス: vehicle={vehicle} track={track} freq={freq} 詳細: {e}", file=sys.stderr)
        print("ヒント: --vehicle/--track/--freq の値を確認してください", file=sys.stderr)
        sys.exit(2)
    except ValueError as e:
        print(f"エラー: 入力が無効です パス: vehicle={vehicle} track={track} 詳細: {e}", file=sys.stderr)
        print("ヒント: 車両/コース名が data/ に存在するか確認してください", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"エラー: シミュレーション失敗 パス: vehicle={vehicle} track={track} 詳細: {e}", file=sys.stderr)
        print("ヒント: --vehicle/--track のパスを確認してください", file=sys.stderr)
        sys.exit(1)
    laptime = float(result.laptime)
    m = int(laptime // 60)
    s = laptime % 60
    if args.as_json:
        out = {
            "vehicle": str(vehicle),
            "track": str(track),
            "laptime": laptime,
            "laptime_str": f"{m:02d}:{s:06.3f}",
            "freq": int(args.freq),
        }
        if hasattr(result, "sector_time"):
            try:
                out["sector_time"] = [float(x) for x in list(result.sector_time)]
            except Exception:
                pass
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(f"laptime: {laptime:.3f}s ({m:02d}:{s:06.3f}) vehicle={vehicle} track={track}")
    if not args.dry_run and args.output:
        try:
            out_path = pathlib.Path(args.output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if args.as_json:
                out_path.write_text(json.dumps({"vehicle": str(vehicle), "track": str(track), "laptime": laptime}, ensure_ascii=False, indent=2), encoding="utf-8")
            else:
                out_path.write_text(f"laptime,{laptime}\n", encoding="utf-8")
        except Exception as e:
            print(f"エラー: 出力失敗 パス: {args.output} 詳細: {e}", file=sys.stderr)
            print("ヒント: 出力先パスの権限を確認してください", file=sys.stderr)
            sys.exit(1)
    sys.exit(0)


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.validate is not None:
        _handle_validate(args.validate, args.as_json)
        return
    if args.headless:
        _handle_headless(args)
        return
    if args.dry_run or args.as_json or args.output is not None:
        if not args.headless:
            print("エラー: --dry-run/--json/--output は --headless と併用してください", file=sys.stderr)
            print("ヒント: 例: --headless --vehicle f1 --track spa --dry-run", file=sys.stderr)
            sys.exit(2)
        _handle_headless(args)
        return
    parser.print_help()
    sys.exit(0)
