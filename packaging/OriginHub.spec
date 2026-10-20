# PyInstaller recipe: builds dist/OriginHub/ (OriginHub.exe + _internal/) from app/.
# Run through packaging/build.ps1, or: pyinstaller packaging/OriginHub.spec --noconfirm
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
APP = ROOT / "app"
sys.path.insert(0, str(APP))          # so the app's own packages can be collected

# Techniques are discovered at run time (pkgutil), so PyInstaller cannot see the imports:
# collect every module of the plugins and of the core, but not their tests.
hidden = [m for m in collect_submodules("techniques") + collect_submodules("core") if ".tests" not in m]
hidden += ["version", "openpyxl", "xlrd"]          # pandas picks the Excel engine at run time

# Files read or copied as files (not imported): the scripts that run inside Origin,
# material profiles and the user guide. Paths mirror app/ so the code finds them unchanged.
datas = [(str(ROOT / "HELP.md"), "."),
         (str(APP / "origin_side" / "origin_common.py"), "origin_side")]
datas += [(str(f), "materials") for f in sorted((APP / "materials").glob("*.toml"))]
for script in sorted((APP / "techniques").glob("*/origin_build.py")):
    datas.append((str(script), f"techniques/{script.parent.name}"))
# Origin graph templates offered by the setup check (app/resources/templates/*.otpu)
datas += [(str(f), "resources/templates") for f in sorted((APP / "resources" / "templates").glob("*.otp*"))]

a = Analysis(
    [str(APP / "main.py")],
    pathex=[str(APP)],
    hiddenimports=hidden,
    datas=datas,
    excludes=["pytest", "tkinter",  # tkinter: only bootstrap.py uses it, never in the frozen app
              "PyQt5", "PySide2", "PySide6", "IPython", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OriginHub",
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="OriginHub", upx=False)
