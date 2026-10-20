"""The QUICKSTART's set-up steps (apps/rhino_plugin/QUICKSTART.md, "What you need", "Install in Rhino", "Getting
updates") checked against the repository, so the guide can't drift: the files it names exist, the Python version is
the one pyproject.toml requires, the commands it says to type are the real ones, and the five Rhino commands it
promises are the five install.py registers, with the exact lines install.py prints."""
import ast
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLUGIN = ROOT / "apps" / "rhino_plugin"
GUIDE = (PLUGIN / "QUICKSTART.md").read_text(encoding="utf-8")
CLONE_TO = "~/Documents/gordium"


def _section(title):
    start = GUIDE.index("## " + title)
    nxt = GUIDE.find("\n## ", start + 3)
    return GUIDE[start:nxt if nxt != -1 else None]


SETUP = _section("What you need (once)")
INSTALL = _section("Install in Rhino (once)")
UPDATES = _section("Getting updates")


def _installed_commands():
    """install.py's COMMANDS dict, read without running it (it imports Rhino)."""
    tree = ast.parse((PLUGIN / "install.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "COMMANDS":
            return ast.literal_eval(node.value)
    raise AssertionError("install.py has no COMMANDS")


def test_every_repository_path_the_guide_names_exists():
    paths = re.findall(re.escape(CLONE_TO) + r"(/[\w./-]+)", GUIDE) + \
        re.findall(r"/Documents/gordium(/[\w./-]+)", GUIDE)
    assert "/apps/rhino_plugin/install.py" in paths
    for p in paths:
        assert (ROOT / p.lstrip("/")).exists(), p
    for script in _installed_commands().values():
        assert (PLUGIN / script).exists(), script
    assert (ROOT / "pyproject.toml").exists()


def test_the_python_version_is_the_one_pyproject_requires():
    required = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["requires-python"]
    version = re.fullmatch(r">=\s*(3\.\d+)", required).group(1)
    assert f"Install Python {version}" in SETUP and f"python{version} --version" in SETUP
    assert f"python{version} -m venv .venv" in SETUP
    assert not set(re.findall(r"python(3\.\d+)", GUIDE)) - {version}           # no other version anywhere


def test_the_setup_commands_are_the_real_ones():
    assert "cd ~/Documents && git clone https://github.com/bz28/gordium.git" in SETUP
    assert ".venv/bin/pip install -e \".[dev]\"" in SETUP
    assert "dev" in tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "optional-dependencies"]
    lines = [ln.strip() for ln in SETUP.splitlines()]
    k = lines.index(f"cd {CLONE_TO}")                                  # the four lines pasted at once, in order
    assert lines[k:k + 4] == [f"cd {CLONE_TO}", "git checkout rhino-ui", "python3.12 -m venv .venv",
                              ".venv/bin/pip install -e \".[dev]\""]
    assert f"cd {CLONE_TO} && git pull" in UPDATES and "Cmd+Q" in UPDATES
    assert f"cd {CLONE_TO} && .venv/bin/pip install -e \".[dev]\"" in UPDATES
    assert f"{CLONE_TO}/apps/rhino_plugin/install.py" in INSTALL


def test_the_five_rhino_commands_match_install_py():
    commands = _installed_commands()
    assert len(commands) == 5
    for alias, script in commands.items():
        assert f"Gordium: {alias} -> {script}" in INSTALL, alias       # the exact line install.py prints
    named = set(re.findall(r"\bGordium[A-Z]\w+", GUIDE))
    assert named <= set(commands), named - set(commands)


def test_the_contents_links_go_to_real_headings():
    def anchor(heading):
        return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")
    anchors = {anchor(h) for h in re.findall(r"^#+ (.+)$", GUIDE, flags=re.M)}
    contents = GUIDE[GUIDE.index("**Contents:**"):GUIDE.index("## ")]
    links = re.findall(r"\]\(#([\w-]+)\)", contents)
    assert len(links) == 5
    for link in links:
        assert link in anchors, link
