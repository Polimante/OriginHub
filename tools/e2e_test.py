"""End-to-end test: builds an Origin project from a data folder, waits for the log,
exports every graph as PNG and closes ONLY the Origin instance it started.

Usage (from the OriginHub folder):
    python tools/e2e_test.py ABS <data folder> [--ref 850] [--thickness 400] [--out <dir>] [--selftest]
    python tools/e2e_test.py XRD <data folder> [--out <dir>]

Outputs <out>/<KIND>_test.opju, <out>/png_<KIND>/*.png and prints the build log.
--selftest changes the Tauc data of the first sample after building and checks
that Origin's Linear Fit recalculates (Eg before/after is written to the log).
"""
import argparse
import sys
import tempfile
import time
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP))
from core import origin_bridge as ob  # noqa: E402
from core.registry import discover  # noqa: E402

ap = argparse.ArgumentParser()
REG = discover()
ap.add_argument("kind", choices=sorted(REG.techniques))
ap.add_argument("folder", type=Path)
ap.add_argument("--ref", type=float, default=850.0, help="baseline wavelength (nm)")
ap.add_argument("--thickness", type=float, default=None, help="thickness (nm) for every sample")
ap.add_argument("--out", type=Path, default=Path(tempfile.gettempdir()) / "originhub_test")
ap.add_argument("--selftest", action="store_true")
ap.add_argument("--timeout", type=float, default=300)
args = ap.parse_args()

tech = REG.techniques[args.kind]
files = sorted(f for f in args.folder.glob("*.*") if (REG.identify(f) or (None,))[0] is tech)
datasets = [d for f in files for d in REG.load(f)[1]]
if not datasets:
    sys.exit(f"no {args.kind} file found in {args.folder}")
for d in datasets:
    d.meta["d_nm"] = args.thickness
args.out.mkdir(parents=True, exist_ok=True)

opts = {"tauc": True, "n": 0.5, "ref_nm": args.ref} if args.kind == "ABS" else {}
payload = ob.build_payload(tech, datasets, args.out / f"{args.kind}_test.opju", opts)
payload["export_png"] = str(args.out / f"png_{args.kind}")
payload["selftest"] = args.selftest

proc, log = ob.launch(payload, tech)
print(f"{len(datasets)} sample(s); Origin pid {proc.pid}: {ob.latest_origin()}")
t0 = time.time()
while time.time() - t0 < args.timeout:
    text = log.read_text(encoding="utf-8") if log.exists() else ""
    if "OK" in text.splitlines() or "Traceback" in text:
        break
    time.sleep(2)
time.sleep(3)
print(log.read_text(encoding="utf-8") if log.exists() else "no log (Origin did not run the script)")
proc.kill()                       # only the instance started here
