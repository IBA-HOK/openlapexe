# -*- coding: utf-8 -*-
"""TDD RED: _atomic_write_text must honor encoding param (shift_jis)."""
import pathlib
from openlapexe.io import _atomic_write_text

def test_atomic_write_encoding_shift_jis(tmp_path: pathlib.Path) -> None:
    # Given: Japanese text that encodes differently in utf-8 vs shift_jis
    text = "こんにちは世界"
    path = tmp_path / "out.txt"
    # When: write with shift_jis
    _atomic_write_text(path, text, encoding="shift_jis")
    raw = path.read_bytes()
    # Then: raw bytes must be shift_jis encoding, not utf-8
    expected_shift_jis = text.encode("shift_jis")
    expected_utf8 = text.encode("utf-8")
    assert raw != expected_utf8, "encoding param ignored: wrote utf-8 instead of shift_jis"
    assert raw == expected_shift_jis, f"expected shift_jis bytes {expected_shift_jis!r} got {raw!r}"
    # also verify round-trip with correct encoding
    assert path.read_text(encoding="shift_jis") == text


def test_atomic_write_default_utf8(tmp_path: pathlib.Path) -> None:
    # Given: default encoding (utf-8)
    text = "héllo — utf8 ✓"
    path = tmp_path / "default.txt"
    # When: write without encoding arg
    _atomic_write_text(path, text)
    # Then: bytes are utf-8 and round-trip works
    assert path.read_bytes() == text.encode("utf-8")
    assert path.read_text(encoding="utf-8") == text


def test_atomic_write_atomic_no_tmp_leak(tmp_path: pathlib.Path) -> None:
    # Given: existing file
    text = "atomic"
    path = tmp_path / "a.txt"
    path.write_text("old", encoding="utf-8")
    # When
    _atomic_write_text(path, text, encoding="utf-8")
    # Then: tmp file not left behind
    assert not path.with_suffix(path.suffix + ".tmp").exists()
    assert path.read_text(encoding="utf-8") == text
