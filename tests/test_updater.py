"""Update check and verified download, against a local web server (never the internet)."""
import functools
import hashlib
import http.server
import json
import threading

import pytest

from core import updater
from version import __version__

TRUSTED = updater.TRUSTED_PREFIX + "v9.9.9/"


def release_json(version="9.9.9", base=TRUSTED, extra_assets=True):
    name = f"OriginHub-Setup-{version}.exe"
    assets = [{"name": name, "size": 10, "browser_download_url": base + name}]
    if extra_assets:
        assets.append({"name": name + ".sha256", "size": 90, "browser_download_url": base + name + ".sha256"})
    return {"tag_name": f"v{version}", "body": "notes", "html_url": "https://github.com/x", "assets": assets}


# ------------------------------------------------------------ versions and release data
@pytest.mark.parametrize("remote, local, newer", [
    ("0.3.0", "0.2.0", True), ("v1.0.0", "0.9.9", True), ("0.10.0", "0.9.0", True),
    ("0.2.0", "0.2.0", False), ("0.1.9", "0.2.0", False),
])
def test_is_newer(remote, local, newer):
    assert updater.is_newer(remote, local) is newer


def test_bad_version_is_rejected():
    with pytest.raises(updater.UpdateError):
        updater.parse_version("latest")


def test_parse_release():
    rel = updater.parse_release(release_json())
    assert rel.version == "9.9.9"
    assert rel.installer_name == "OriginHub-Setup-9.9.9.exe"
    assert rel.sha256_url.endswith(".exe.sha256")


def test_release_without_checksum_is_refused():
    with pytest.raises(updater.UpdateError, match="no installer"):
        updater.parse_release(release_json(extra_assets=False))


def test_download_from_elsewhere_is_refused(monkeypatch):
    monkeypatch.delenv("ORIGINHUB_UPDATE_API", raising=False)
    with pytest.raises(updater.UpdateError, match="unexpected download location"):
        updater.parse_release(release_json(base="https://evil.example.com/"))


def test_expected_sha256():
    h = "a" * 64
    assert updater.expected_sha256(f"{h}  OriginHub-Setup-1.0.0.exe\n", "OriginHub-Setup-1.0.0.exe") == h
    assert updater.expected_sha256(h.upper(), "x.exe") == h
    with pytest.raises(updater.UpdateError):
        updater.expected_sha256("not a hash", "x.exe")


def test_installer_restarts_the_app():
    args = updater.installer_args(updater.Path("setup.exe"))
    assert "/SILENT" in args and "/RELAUNCH=1" in args


def test_source_checkout_does_not_self_update():
    assert updater.can_self_update() is False


# ------------------------------------------------------------ local server
@pytest.fixture
def server(tmp_path, monkeypatch):
    """Serves tmp_path/www over HTTP; ORIGINHUB_UPDATE_API points to its latest.json."""
    www = tmp_path / "www"
    www.mkdir()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(www))
    handler.log_message = lambda *a: None
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}/"
    monkeypatch.setenv("ORIGINHUB_UPDATE_API", base + "latest.json")
    yield www, base
    httpd.shutdown()


def publish(www, base, version, payload=b"installer bytes" * 1000, sha=None):
    name = f"OriginHub-Setup-{version}.exe"
    (www / name).write_bytes(payload)
    (www / (name + ".sha256")).write_text(f"{sha or hashlib.sha256(payload).hexdigest()}  {name}\n")
    (www / "latest.json").write_text(json.dumps(release_json(version, base)))


def test_newer_release_is_found_and_downloaded(server, tmp_path):
    www, base = server
    publish(www, base, "99.0.0")
    rel = updater.check()
    assert rel and rel.version == "99.0.0"
    seen = []
    path = updater.download(rel, tmp_path / "dl", progress=lambda d, t: seen.append((d, t)))
    assert path.read_bytes() == (www / rel.installer_name).read_bytes()
    assert seen and seen[-1][0] == seen[-1][1] == path.stat().st_size


def test_same_version_means_up_to_date(server):
    www, base = server
    publish(www, base, __version__)
    assert updater.check() is None


def test_damaged_download_is_deleted_and_not_installed(server, tmp_path):
    www, base = server
    publish(www, base, "99.0.0", sha="0" * 64)
    rel = updater.check()
    with pytest.raises(updater.UpdateError, match="SHA-256 mismatch"):
        updater.download(rel, tmp_path / "dl")
    assert not (tmp_path / "dl" / rel.installer_name).exists()


def test_offline_is_a_clean_error(monkeypatch):
    monkeypatch.setenv("ORIGINHUB_UPDATE_API", "http://127.0.0.1:9/latest.json")    # nothing listens there
    with pytest.raises(updater.UpdateError, match="could not reach"):
        updater.check(timeout=2)
