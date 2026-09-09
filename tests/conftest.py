"""Ensure project root and src are on sys.path for `import app` and `openlapexe`."""
import pathlib
import sys

_root = pathlib.Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
_src = _root / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))
