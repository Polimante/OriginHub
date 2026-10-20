"""Common payload, Origin discovery and the run folder handed to Origin (no Origin needed)."""
import json
import py_compile

import pytest

from core import origin_bridge as ob
from core.registry import discover

REG = discover()


@pytest.mark.parametrize("key", sorted(REG.techniques))
def test_run_folder_has_only_this_technique(key, monkeypatch, tmp_path):
    """launch() writes payload, common helpers, ONLY this technique's script and the launcher."""
    calls = []
    monkeypatch.setattr(ob, "WORK", tmp_path / "work")
    monkeypatch.setattr(ob.subprocess, "Popen", lambda cmd: calls.append(cmd) or "proc")
    tech = REG.techniques[key]
    payload = {"kind": key, "groups": [], "template": "line", "save_path": ""}
    _, log = ob.launch(payload, tech, exe=tmp_path / "Origin64.exe")

    (cmd,) = calls
    assert isinstance(cmd, str)                      # one string: a list double-escapes the quotes
    assert cmd.startswith(f'"{tmp_path / "Origin64.exe"}" -rs run -pyf "')
    (run_dir,) = (tmp_path / "work").iterdir()
    assert sorted(p.name for p in run_dir.iterdir()) == ["launch.py", "origin_build.py",
                                                         "origin_common.py", "payload.json"]
    assert (run_dir / "origin_build.py").read_text(encoding="utf-8") == tech.origin_script.read_text(encoding="utf-8")
    launcher = (run_dir / "launch.py").read_text(encoding="utf-8")
    assert launcher.startswith(f'PAYLOAD = r"{run_dir / "payload.json"}"')
    assert str(run_dir) in launcher
    py_compile.compile(str(run_dir / "launch.py"), doraise=True)
    assert json.loads((run_dir / "payload.json").read_text(encoding="utf-8"))["kind"] == key
    assert log == run_dir / "payload.json.log"


def test_two_exports_in_the_same_second_do_not_collide(monkeypatch, tmp_path):
    monkeypatch.setattr(ob, "WORK", tmp_path)
    monkeypatch.setattr(ob.time, "strftime", lambda fmt: "20260101_120000")
    tech = REG.techniques["XRD"]
    a, _ = ob.prepare_run({"kind": "XRD"}, tech)
    b, _ = ob.prepare_run({"kind": "XRD"}, tech)
    assert a.parent != b.parent


def test_find_origins_parses_install_folders(monkeypatch, tmp_path):
    for name in ("Origin2018", "Origin2025b", "OriginPro 2023", "NotOrigin"):
        (tmp_path / "OriginLab" / name).mkdir(parents=True)
        (tmp_path / "OriginLab" / name / "Origin64.exe").write_text("")
    for var in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        monkeypatch.setenv(var, str(tmp_path))
    found = ob.find_origins()
    assert [v for v, _ in found] == ["2025b", "2023", "2018"]
    assert ob.latest_origin().parent.name == "Origin2025b"
