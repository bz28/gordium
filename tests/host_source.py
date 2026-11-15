"""The one way a test reads a host's source text (the Rhino plugin today; a Revit add-in later).

Why: about 270 tests read the Rhino plugin's own source to prove something about it. Reading it through one
helper means a second host only has to say where its files are, and every such read says WHY it reads:

  purpose="lint"    a rule any host must follow (every callback guarded, no console windows, the file compiles,
                    no unsafe text encoding). These run over host_files(host) for each host.
  purpose="wiring"  only proves the plugin calls X (a name or a line is present). When a function moves out of
                    the plugin, such a check is replaced by X's own unit test.

A test never opens a plugin file itself: packages/design_checker/tests/test_host_source.py fails if one does.
Tests reach this module as `from host_source import ...` (the repo-root conftest.py puts tests/ on sys.path).
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PURPOSES = ("lint", "wiring")

# part name -> file, per host. "plugin" is the host's main file, "ui" its windows; "logic" is the helper module the
# host calls (packages/design_checker/design_checker/rhino_logic.py), whose host-neutral half now lives in host_core/
# (CORE_DIR, shared by every host): logic_files() and logic_text() read both, as the one module they were.
CORE_DIR = REPO / "packages/design_checker/design_checker/host_core"
_RHINO_DIR = REPO / "apps/rhino_plugin"
HOSTS = {
    "rhino": {
        "dir": _RHINO_DIR,
        "parts": {
            "plugin": _RHINO_DIR / "gordium_rhino.py",
            "ui": _RHINO_DIR / "gordium_ui.py",
            "logic": REPO / "packages/design_checker/design_checker/rhino_logic.py",
            "check": _RHINO_DIR / "gordium_check.py",
            "panel": _RHINO_DIR / "gordium_panel.py",
            "install": _RHINO_DIR / "install.py",
            "off": _RHINO_DIR / "gordium_off.py",
        },
        "lint_parts": ("plugin", "ui"),        # the files a structural rule runs over
        "scripts": _RHINO_DIR / "tests",       # the *_in_rhino.py scripts that run inside the host
    },
}


def _host(host):
    if host not in HOSTS:
        raise KeyError(f"unknown host {host!r}; known: {sorted(HOSTS)}")
    return HOSTS[host]


def _check(purpose):
    if purpose not in PURPOSES:
        raise ValueError(f"purpose must be one of {PURPOSES}, not {purpose!r}")


def host_dir(host):
    """The host's folder (what a test puts on sys.path to import the plugin's modules)."""
    return _host(host)["dir"]


def host_files(host, *, scripts=False):
    """The host's source files a structural (lint) rule runs over; with scripts=True also its in-host test scripts."""
    h = _host(host)
    files = [h["parts"][p] for p in h["lint_parts"]]
    return files + (host_scripts(host) if scripts else [])


def host_scripts(host):
    """The host's in-host test scripts (apps/rhino_plugin/tests/*_in_rhino.py), sorted."""
    return sorted(_host(host)["scripts"].glob("*_in_rhino.py"))


def host_tree(host):
    """Every Python file under the host's folder (for a lint that must see them all, such as "each one compiles")."""
    return sorted(_host(host)["dir"].rglob("*.py"))


def host_command_files(host):
    """The host's command files (apps/rhino_plugin/gordium_*.py: one file per command an architect can run)."""
    return sorted(_host(host)["dir"].glob("gordium_*.py"))


def host_path(host, part):
    """The path of one named part ("plugin", "ui", "logic", ...), for a test that needs the file, not its text."""
    return _host(host)["parts"][part]


def core_files():
    """host_core's modules (facts, streets, lookup, start_box, place...), sorted: the code every host calls."""
    return sorted(CORE_DIR.glob("*.py"))


def logic_files(host):
    """The host's logic module and the host_core modules it re-exports: everything `logic.X` can name."""
    return [host_path(host, "logic"), *core_files()]


def logic_text(host, *, purpose):
    """The text of logic_files(host), one after another: what the logic module's own text was before host_core
    (a wiring check that a line or name is there reads this, so a line that moved is still found)."""
    _check(purpose)
    return "\n".join(p.read_text(encoding="utf-8") for p in logic_files(host))


def host_text(host, part, *, purpose):
    """The text of one named part of the host's source."""
    _check(purpose)
    return host_path(host, part).read_text(encoding="utf-8")


def host_text_of(path, *, purpose):
    """The text of one of host_files()/host_scripts()'s paths."""
    _check(purpose)
    return Path(path).read_text(encoding="utf-8")


def host_script(host, name, *, purpose):
    """The text of one in-host test script, by file name (for example "context_in_rhino.py")."""
    _check(purpose)
    return (_host(host)["scripts"] / name).read_text(encoding="utf-8")


def host_doc(host, name, *, purpose):
    """The text of one document that ships with the host's plugin (QUICKSTART.md, GUIDE.md, README.md)."""
    _check(purpose)
    return (_host(host)["dir"] / name).read_text(encoding="utf-8")
