"""Setup check: Origin, work folder, graph templates; fixes only copy, never overwrite."""
import json
from pathlib import Path

import pytest

from core import environment as env


@pytest.fixture
def uff(tmp_path):
    """A fake Origin User Files Folder, reported by Origin through origin_paths.json."""
    work = tmp_path / "work"
    folder = tmp_path / "User Files"
    work.mkdir()
    folder.mkdir()
    (work / env.ORIGIN_PATHS).write_text(json.dumps({"user_files": str(folder)}))
    return work, folder


@pytest.fixture
def bundled(tmp_path, monkeypatch):
    d = tmp_path / "templates"
    d.mkdir()
    (d / "PadraoLinha.otpu").write_bytes(b"template v2")
    monkeypatch.setattr(env, "TEMPLATES_DIR", d)
    return d


@pytest.mark.parametrize("found, status", [
    ([], "error"), ([("2018", Path("o.exe"))], "error"), ([("2025b", Path("o.exe"))], "ok"),
])
def test_origin(monkeypatch, found, status):
    monkeypatch.setattr(env.ob, "find_origins", lambda: found)
    assert env.check_origin().status == status


def test_work_folder(tmp_path):
    assert env.check_work_folder(tmp_path / "OriginHub").status == "ok"
    assert env.check_work_folder(tmp_path / "Área").status == "warning"     # Origin's command line dislikes accents


def test_user_files_folder_reported_by_origin(uff):
    work, folder = uff
    assert env.user_files_folder(work) == folder


def test_missing_template_is_offered_and_installed(uff, bundled):
    work, folder = uff
    c = env.check_templates(work)
    assert c.status == "warning" and c.fix == "install_templates"
    assert "Installed: PadraoLinha.otpu" in env.apply_fix(c.fix, work)
    assert (folder / "PadraoLinha.otpu").read_bytes() == b"template v2"
    assert env.check_templates(work).status == "ok"


def test_existing_template_is_never_overwritten(uff, bundled):
    work, folder = uff
    (folder / "PadraoLinha.otpu").write_bytes(b"the user's own version")
    assert env.install_templates(work) == []
    assert (folder / "PadraoLinha.otpu").read_bytes() == b"the user's own version"


def test_no_user_files_folder(tmp_path, monkeypatch, bundled):
    monkeypatch.setattr(env, "documents_folder", lambda: tmp_path / "nowhere")
    c = env.check_templates(tmp_path)
    assert c.status == "warning" and not c.fix
    with pytest.raises(RuntimeError, match="open Origin once"):
        env.install_templates(tmp_path)


def test_a_crashing_check_does_not_stop_the_others(monkeypatch, tmp_path):
    def boom():
        raise OSError("disk on fire")
    monkeypatch.setattr(env, "check_origin", boom)
    checks = env.run_checks(tmp_path)
    assert len(checks) == 3
    assert checks[0].key == "internal" and "disk on fire" in checks[0].detail


def test_documents_folder_exists():
    assert env.documents_folder().is_dir()


def test_padraolinha_is_bundled():
    """The default graph template (Origin's User Files) ships with the app."""
    assert "PadraoLinha" in [p.stem for p in env.bundled_templates()]
