"""The QUICKSTART's set-up steps (apps/rhino_plugin/QUICKSTART.md: "What you need", "Install in Rhino", "Getting
updates" and "On Windows") checked against the repository, so the guide can't drift: the files it names exist, the
Pythons it offers are exactly pyproject.toml's requires-python range (both ends), the commands it says to type are the real ones (Mac and
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


def _python_range():
    """pyproject's requires-python as (oldest supported, first unsupported), e.g. ((3, 12), (3, 15))."""
    m = re.fullmatch(r">=\s*(\d+)\.(\d+)\s*,\s*<\s*(\d+)\.(\d+)", PYPROJECT["project"]["requires-python"])
    assert m, "requires-python must be '>=3.X,<3.Y'"
    a, b, c, d = map(int, m.groups())
    return (a, b), (c, d)


def _supported():
    (major, lo), (_, hi) = _python_range()
    return [f"{major}.{n}" for n in range(lo, hi)]                     # e.g. 3.12, 3.13, 3.14


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


def test_the_python_versions_are_pyprojects_range_both_ends():
    versions = _supported()
    oldest, newest = versions[0], versions[-1]
    (major, _), (_, hi) = _python_range()
    unsupported = f"{major}.{hi}"
    span = f"Install Python {oldest} to {newest}** ({', '.join(versions[:-1])} or {newest}; {unsupported} not yet supported"
    assert SETUP.count(span) == 1 and WINDOWS.count(span) == 1
    assert GUIDE.count(f"needs {oldest} to {newest}; {unsupported} not yet supported") == 1      # Troubleshooting
    # every version the steps tell you to install or type is in the range (3.15 is named only as unsupported)
    typed = re.findall(r"(?:python|py -|Python )(3\.\d+)", SETUP + WINDOWS + _section("Troubleshooting"))
    assert typed and set(typed) <= set(versions), set(typed) - set(versions)
    assert f"python{newest} --version" in SETUP and "py list" in WINDOWS
    win = _lines(WINDOWS)
    assert win[win.index(f"py install {newest}") + 1] == "py list"     # the Install Manager adds the version
    assert f"run `py install {newest}` first" in _section("Troubleshooting")
    assert f"{unsupported} not yet supported" in WINDOWS and f"(not {unsupported})" in SETUP + WINDOWS


def test_a_bare_python_is_never_used_to_make_the_venv():
    # a plain `python3` / `py` can pick an unsupported Python (a tester's `py` chose 3.15 and pip then needed a
    # C++ compiler); every venv line names a version from the range
    for line in _lines(GUIDE):
        if "-m venv" in line:
            assert re.fullmatch(r"(python|py -)(3\.\d+) -m venv \.venv", line), line
            assert re.match(r"(?:python|py -)(3\.\d+)", line).group(1) in _supported(), line


def test_the_mac_commands_are_the_real_ones():
    assert "dev" in PYPROJECT["project"]["optional-dependencies"]
    assert "cd ~/Documents && git clone https://github.com/bz28/gordium.git" in SETUP
    lines = _lines(SETUP)
    k = lines.index(f"cd {CLONE_TO}")                                  # the four lines pasted at once, in order
    newest = _supported()[-1]
    assert lines[k:k + 4] == [f"cd {CLONE_TO}", "git checkout rhino-ui", f"python{newest} -m venv .venv",
                              f".venv/bin/{PIP}"]
    k = lines.index(f"cd {CLONE_TO}", k + 1)                           # delete and redo with a supported Python
    assert lines[k:k + 4] == [f"cd {CLONE_TO}", "rm -rf .venv", f"python{newest} -m venv .venv", f".venv/bin/{PIP}"]
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
    newest = _supported()[-1]
    assert lines[k:k + 4] == [f"cd {WIN_CLONE_TO}", "git checkout rhino-ui", f"py -{newest} -m venv .venv",
                              rf".\.venv\Scripts\{PIP}"]
    k = lines.index(f"cd {WIN_CLONE_TO}", k + 1)                       # delete and redo with a supported Python
    assert lines[k:k + 4] == [f"cd {WIN_CLONE_TO}", "Remove-Item -Recurse -Force .venv", f"py -{newest} -m venv .venv",
                              rf".\.venv\Scripts\{PIP}"]
    assert "Microsoft Visual C++ 14.0 or greater is required" in WINDOWS
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
