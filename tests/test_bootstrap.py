"""Source start-up: missing packages are installed only after the user says yes."""
import bootstrap


class Calls:
    def __init__(self, answer=True, install_ok=True, fixes=True):
        self.answer, self.install_ok, self.fixes = answer, install_ok, fixes
        self.asked, self.installed, self.told = [], 0, []
        self.missing = {"PyQt6", "pyqtgraph"}

    def find_spec(self, mod):
        return None if mod in self.missing else object()

    def ask(self, text):
        self.asked.append(text)
        return self.answer

    def install(self):
        self.installed += 1
        if self.fixes:
            self.missing = set()
        return self.install_ok, "pip log"

    def tell(self, text, error=False):
        self.told.append(text)

    def run(self):
        return bootstrap.ensure_packages(self.find_spec, self.ask, self.install, self.tell)


def test_nothing_missing_starts_without_asking():
    c = Calls()
    c.missing = set()
    assert c.run() is True
    assert not c.asked and not c.installed


def test_user_agrees_packages_are_installed():
    c = Calls(answer=True)
    assert c.run() is True
    assert "PyQt6, pyqtgraph" in c.asked[0]
    assert c.installed == 1


def test_user_declines_nothing_is_installed():
    c = Calls(answer=False)
    assert c.run() is False
    assert c.installed == 0
    assert "pip install -r" in c.told[0]


def test_failed_installation_is_reported():
    c = Calls(answer=True, install_ok=False, fixes=False)
    assert c.run() is False
    assert "still missing" in c.told[0] and "pip log" in c.told[0]


def test_requirements_list_matches_requirements_txt():
    names = {line.split(">")[0].split("=")[0].strip().lower()
             for line in bootstrap.REQUIREMENTS.read_text().splitlines() if line.strip() and not line.startswith("#")}
    assert names == {p.lower() for p in bootstrap.REQUIRED.values()}
