"""The QUICKSTART's set-up steps (apps/rhino_plugin/QUICKSTART.md: "What you need", "Install in Rhino", "Getting
updates" and "On Windows") checked against the repository, so the guide can't drift: the files it names exist, the
oldest Python it accepts is the one pyproject.toml requires, the commands it says to type are the real ones (Mac and
Windows), and the five Rhino commands it promises are the five install.py registers, with the lines it prints."""
import ast
import re
import tomllib
from pathlib import Path

from design_checker.rhino_logic import venv_python

ROOT = Path(__file__).resolve().parents[3]
PLUGIN = ROOT / "apps" / "rhino_plugin"
GUIDE = (PLUGIN / "QUICKSTART.md").read_text(encoding="utf-8")
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
CLONE_TO = "~/Documents/gordium"
WIN_CLONE_TO = r"$HOME\Documents\gordium"
PIP = 'pip install -e ".[dev]"'


def _section(title):
    start = GUIDE.index("\n## " + title + "\n")
    nxt = GUIDE.find("\n## ", start + 4)
    return GUIDE[start:nxt if nxt != -1 else None]


SETUP = _section("What you need (once)")
INSTALL = _section("Install in Rhino (once)")
UPDATES = _section("Getting updates")
WINDOWS = _section("On Windows")


def _lines(text):
    return [ln.strip() for ln in text.splitlines()]


def _installed_commands():
    """install.py's COMMANDS dict, read without running it (it imports Rhino)."""
    tree = ast.parse((PLUGIN / "install.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "COMMANDS":
            return ast.literal_eval(node.value)
    raise AssertionError("install.py has no COMMANDS")


def _minimum_python():
    return tuple(int(n) for n in re.fullmatch(r">=\s*(\d+)\.(\d+)", PYPROJECT["project"]["requires-python"]).groups())


def test_every_repository_path_the_guide_names_exists():
    paths = re.findall(re.escape(CLONE_TO) + r"(/[\w./-]+)", GUIDE) + \
        re.findall(r"/Documents/gordium(/[\w./-]+)", GUIDE)
    assert "/apps/rhino_plugin/install.py" in paths
    for p in paths:
        assert (ROOT / p.lstrip("/")).exists(), p
    # the click-through routes ("Documents → gordium → apps → rhino_plugin → `install.py`"), Mac and Windows
    routes = re.findall(r"Documents → gordium((?: → \w+)+)(?:, pick| →) `([\w.]+)`", GUIDE)
    assert len(routes) == 2
    for folders, name in routes:
        assert (ROOT.joinpath(*folders.split(" → ")[1:]) / name).exists(), (folders, name)
    for script in _installed_commands().values():
        assert (PLUGIN / script).exists(), script


def test_the_python_versions_start_at_the_one_pyproject_requires():
    major, minor = _minimum_python()
    oldest = f"{major}.{minor}"
    assert SETUP.count(f"Install Python {oldest} or newer") == 1 and WINDOWS.count(f"Install Python {oldest} or newer") == 1
    assert f"a version below {oldest}" in SETUP
    named = {tuple(map(int, v.split("."))) for v in re.findall(r"(?:Python |python|`)(3\.\d+)\b", SETUP + WINDOWS)}
    named.discard((3, 9))                                            # the Mac's own old Python, named as too old
    assert min(named) == (major, minor), named                         # nothing older is offered as working
    assert "python3 --version" in SETUP and "py --version" in WINDOWS


def test_the_mac_commands_are_the_real_ones():
    assert "dev" in PYPROJECT["project"]["optional-dependencies"]
    assert "cd ~/Documents && git clone https://github.com/bz28/gordium.git" in SETUP
    lines = _lines(SETUP)
    k = lines.index(f"cd {CLONE_TO}")                                  # the four lines pasted at once, in order
    assert lines[k:k + 4] == [f"cd {CLONE_TO}", "git checkout rhino-ui", "python3 -m venv .venv", f".venv/bin/{PIP}"]
    assert venv_python(str(ROOT), "posix").endswith("/.venv/bin/python")   # where the plugin looks for that venv
    assert f"cd {CLONE_TO} && git pull" in UPDATES and "Cmd+Q" in UPDATES
    assert f"cd {CLONE_TO} && .venv/bin/{PIP}" in UPDATES
    assert f"{CLONE_TO}/apps/rhino_plugin/install.py" in INSTALL


def test_the_windows_commands_are_the_real_ones():
    assert "hasn't been tested yet" in WINDOWS
    lines = _lines(WINDOWS)
    k = lines.index(r"cd $HOME\Documents")
    assert lines[k:k + 2] == [r"cd $HOME\Documents", "git clone https://github.com/bz28/gordium.git"]
    k = lines.index(f"cd {WIN_CLONE_TO}")
    assert lines[k:k + 4] == [f"cd {WIN_CLONE_TO}", "git checkout rhino-ui", "py -m venv .venv",
                              rf".\.venv\Scripts\{PIP}"]
    # the venv's Python is where the plugin looks for it on Windows
    assert venv_python("C:\\gordium", "nt") == "C:\\gordium\\.venv\\Scripts\\python.exe"
    assert f"cd {WIN_CLONE_TO}; git pull" in WINDOWS and "File → Exit" in WINDOWS
    assert "Add python.exe to PATH" in WINDOWS and "git-scm.com" in WINDOWS


def test_the_five_rhino_commands_match_install_py():
    commands = _installed_commands()
    assert len(commands) == 5
    for alias, script in commands.items():
        assert f"Gordium: {alias} -> {script}" in INSTALL, alias       # the exact line install.py prints
    named = set(re.findall(r"\bGordium[A-Z]\w+", GUIDE))
    assert named <= set(commands), named - set(commands)


def test_every_link_inside_the_guide_goes_to_a_real_heading():
    def anchor(heading):
        return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")
    anchors = {anchor(h) for h in re.findall(r"^#+ (.+)$", GUIDE, flags=re.M)}
    contents = GUIDE[GUIDE.index("**Contents:**"):GUIDE.index("\n## ")]
    assert len(re.findall(r"\]\(#([\w-]+)\)", contents)) == 6
    for link in re.findall(r"\]\(#([\w-]+)\)", GUIDE):
        assert link in anchors, link
