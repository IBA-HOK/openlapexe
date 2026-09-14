#!/bin/bash
# verify_surface.sh - SURFACE verification: conformance + CLI headless export + evidence log.
# Outputs: data/reference/cli_evidence.log, /tmp/ggv.csv, /tmp/surface_*.png
# Usage: bash scripts/verify_surface.sh (optionally under xvfb-run for Tk PNGs)
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$ROOT/data/reference/cli_evidence.log"
mkdir -p "$ROOT/data/reference"
{
echo "date: $(date -u +%FT%TZ)"
echo "== conformance =="
python3 -m pytest tests/regression/test_matlab_conformance_red.py -v 2>&1 | tail -n 16
echo "== headless export =="
PYTHONPATH=src python3 -m openlapexe.cli --headless --vehicle f1 --track spa --dry-run 2>&1 | head -n 10
echo "== laptime =="
PYTHONPATH=src python3 -c "from openlapexe.solver import simulate_full; r=simulate_full('f1','spa',50); print('laptime_50Hz:', repr(r.laptime))" 2>&1 | tail -n 2
echo "== GGV csv =="
PYTHONPATH=src python3 -c "
import sys; sys.path.insert(0,'src')
import numpy as np
from openlapexe.vehicle import Vehicle47
veh = Vehicle47.from_json('f1')
speeds = np.linspace(5.0, 80.0, 20)
ggv = veh.compute_ggv(speeds)
ax_min = np.asarray(ggv.get('ax_min')); ax_max = np.asarray(ggv.get('ax_max')); ay_max = np.asarray(ggv.get('ay_max'))
print('ax_min<0:', bool(np.any(ax_min < -1e-6)), 'ax_max>0:', bool(np.any(ax_max > 1e-6)), 'rows:', len(ax_min))
np.savetxt('/tmp/ggv.csv', np.column_stack([speeds, ax_min, ax_max, ay_max]), delimiter=',', header='v,ax_min,ax_max,ay_max')
" 2>&1 | tail -n 3
ls -lh /tmp/ggv.csv 2>&1
echo "== Tk surfaces =="
python3 -c "import tkinter; print('tkinter ok')" 2>&1 | tail -n 1
echo "== Tk chart PNGs (needs display; skipped gracefully if unavailable) =="
PYTHONPATH=src python3 -c '
import sys
try:
    import tkinter as tk
    from openlapexe.solver import simulate_full
    import openlapexe.gui.charts_results as mod
    import numpy as np
    result = simulate_full("f1", "spa")
    root = tk.Tk()
    root.geometry("900x700+10+10")
    root.deiconify(); root.lift(); root.update_idletasks(); root.update()
    for name, cls in [("ggv", mod.ResultsGGV3DChart), ("steer", mod.ResultsSteerChart), ("trackmap", mod.ResultsTrackMapChart)]:
        try:
            c = cls(root, width=800, height=600); c.pack()
            root.update_idletasks(); root.update()
            c.plot(result); root.update_idletasks(); root.update()
            print(name, "items=", len(c.find_all()), "draw_count=", getattr(c, "_draw_count", "?"))
            c.postscript(file="/tmp/surface_%s.ps" % name, colormode="color")
            if name == "steer":
                d = np.asarray(c._delta, dtype=float); b = np.asarray(c._beta, dtype=float); h = np.asarray(c._handle, dtype=float)
                print("steer max|delta|=%.2f max|beta|=%.2f max|handle|=%.1f" % (float(np.abs(d).max()), float(np.abs(b).max()), float(np.abs(h).max())))
            c.destroy()
        except Exception as e:
            print(name, "chart skipped:", e)
    root.destroy()
    print("Tk PNG capture done")
except Exception as e:
    print("Tk PNG capture skipped:", e)
' 2>&1 | tail -n 10
for f in ggv steer trackmap; do
  if [ -f "/tmp/surface_$f.ps" ]; then
    gs -dBATCH -dNOPAUSE -sDEVICE=png16m -r100 -sOutputFile="/tmp/surface_$f.png" "/tmp/surface_$f.ps" >/dev/null 2>&1 && echo "$f png ok" || echo "$f png FAIL"
  fi
done
python3 -c '
try:
    from PIL import Image
    import numpy as np
    for p in ["ggv", "steer", "trackmap"]:
        a = np.asarray(Image.open("/tmp/surface_%s.png" % p).convert("L"))
        nw = (a < 250).sum()
        print(p, "nonwhite=%.2f%%" % (100.0 * nw / a.size))
except Exception as e:
    print("PNG stats skipped:", e)
' 2>&1 | tail -n 4
} 2>&1 | tee "$LOG"
echo "wrote $LOG"
