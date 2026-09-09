# -*- coding: utf-8 -*-
from __future__ import annotations

import sys

from openlapexe.cli import main as cli_main


def main() -> None:
    if len(sys.argv) > 1 and any(a.startswith("-") for a in sys.argv[1:]):
        cli_main()
        return
    if len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h"):
        cli_main()
        return
    try:
        from openlapexe.gui.shell import App2

        app = App2()
        app.mainloop()
    except Exception as e:
        print(f"エラー: GUI起動失敗: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
