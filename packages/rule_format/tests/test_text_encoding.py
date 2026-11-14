"""Every text file Gordium reads or writes says encoding="utf-8".

Without it Python uses the computer's own code page: on Windows that is cp1252, which turns the law's UTF-8 "—"
into "â€”" (so no quote matched its page and every check refused, found on a real Windows 11 machine), and can't
read some extracted-text bytes at all. Python only makes UTF-8 the default in 3.15 (PEP 686), and Rhino runs 3.9.
The scan reads the code (no regex on lines): each text-mode open / read_text / write_text, and each subprocess
that talks in text, names its encoding. Binary mode ("rb", "wb") has none and is left alone.
"""

import ast
import os
import subprocess
import sys
import warnings

import pytest

from rule_format.rulebook import REPO, jurisdictions
from host_source import host_path, host_script, host_text, host_tree

# Code and tests alike. Dated eval records (evals/) are frozen as they were run, never run again by CI.
SCANNED = sorted(p for p in [*(REPO / "packages").rglob("*.py"), *host_tree("rhino")]
                 if "evals" not in p.relative_to(REPO).parts)
assert len(SCANNED) > 50

# `x.open(...)` that are not files: pdfplumber reads a PDF (binary); in the Rhino tests `docs.open` opens a template;
# ifcopenshell parses an IFC model itself (its own STEP reader, no text-mode file).
NOT_FILES = {"pdfplumber", "docs", "webbrowser", "ifcopenshell"}
SUBPROCESS = {"Popen", "run", "check_output", "call", "check_call"}


def _const(node):
    return node.value if isinstance(node, ast.Constant) else None


def _unencoded(source: str) -> list[int]:
    """Line numbers of the text-mode file calls (and text-mode subprocesses) that name no encoding."""
    return [node.lineno for node in _unencoded_calls(source)]


def _unencoded_calls(source: str) -> list[ast.Call]:
    found = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)                          # an odd escape in a docstring
        tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        kw = {k.arg: k.value for k in node.keywords}
        f, mode = node.func, None
        if isinstance(f, ast.Name) and f.id == "open":                          # open(path, mode)
            mode = kw.get("mode", node.args[1] if len(node.args) > 1 else None)
        elif isinstance(f, ast.Attribute) and f.attr == "open":                 # Path.open(mode), io.open(path, mode)
            if isinstance(f.value, ast.Name) and f.value.id in NOT_FILES:
                continue
            if isinstance(f.value, ast.Name) and f.value.id in ("io", "codecs"):
                mode = kw.get("mode", node.args[1] if len(node.args) > 1 else None)
            else:
                mode = kw.get("mode", node.args[0] if node.args else None)
        elif isinstance(f, ast.Attribute) and f.attr in ("read_text", "write_text"):
            pass
        elif isinstance(f, ast.Attribute) and f.attr in SUBPROCESS and isinstance(f.value, ast.Name) \
                and f.value.id == "subprocess":
            if not any(_const(kw.get(k)) is True for k in ("text", "universal_newlines")):
                continue                                                         # bytes: nothing is decoded
        else:
            continue
        if mode is not None and isinstance(_const(mode), str) and "b" in _const(mode):
            continue                                                             # binary: no encoding
        if "encoding" not in kw:
            found.append(node)
    return found


def test_every_text_file_call_names_its_encoding():
    found = [f"{p.relative_to(REPO).as_posix()}:{n}" for p in SCANNED
             for n in _unencoded(p.read_text(encoding="utf-8"))]
    assert found == [], 'add encoding="utf-8" (Windows reads cp1252 otherwise): ' + ", ".join(found)


@pytest.mark.parametrize("line", [
    "open(p)", "open(p, 'w')", "open(p, mode='a')", "p.open()", "p.open('a')", "p.read_text()",
    "p.read_text(errors='ignore')", "p.write_text(s)", "json.dump(x, open(p, 'w'))", "io.open(p, 'r')",
    "subprocess.run(a, text=True)", "subprocess.Popen(a, universal_newlines=True)", "open(p, m)",
])
def test_the_scan_catches_a_text_call_without_an_encoding(line):
    assert _unencoded(line) == [1]


@pytest.mark.parametrize("line", [
    "open(p, 'rb')", "open(p, mode='wb')", "p.open('rb')", "p.read_bytes()", "p.write_bytes(b)",
    "open(p, encoding='utf-8')", "p.read_text(encoding='utf-8')", "p.open('a', encoding='utf-8')",
    "pdfplumber.open(p)", "docs.open('Large Objects - Feet')", "subprocess.run(a, capture_output=True)",
    "subprocess.Popen(a, universal_newlines=True, encoding='utf-8')",
])
def test_the_scan_leaves_binary_and_encoded_calls_alone(line):
    assert _unencoded(line) == []


def test_every_venv_python_the_plugin_starts_runs_in_utf8_mode():
    """A second guard for third-party code that opens files itself: the checker Rhino starts runs in UTF-8 mode."""
    for name, source in ((host_path("rhino", "plugin").name, host_text("rhino", "plugin", purpose="lint")),
                         ("scenarios_in_rhino.py", host_script("rhino", "scenarios_in_rhino.py", purpose="lint"))):
        starts = source.count("_python(), ")
        assert starts and source.count('env["PYTHONUTF8"] = "1"') == starts, name
    worker = host_text("rhino", "plugin", purpose="lint").split("def _worker(", 1)[1]
    worker = worker.split("\ndef ", 1)[0]
    assert worker.index('env["PYTHONUTF8"] = "1"') < worker.index("ui.spawn(")    # (no console on Windows)


def test_every_command_prints_in_utf8():
    """Every module run as a command (`python -m <package>`, `python -m design_checker.scenarios`...) sets its output
    to UTF-8 first (rulebook.utf8_console), or on Windows a command whose output goes to a file, a pipe or CI
    crashes on its first ✓ (found by the Windows CI job)."""
    guard = 'if __name__ == "__main__":'
    commands = [p for p in (REPO / "packages").glob("*/*/*.py")
                if p.parent.name != "tests" and guard in p.read_text(encoding="utf-8")]
    assert len(commands) >= 9 and any(p.name == "scenarios.py" for p in commands)
    missing = [p.relative_to(REPO).as_posix() for p in commands
               if "utf8_console()" not in p.read_text(encoding="utf-8").split(guard, 1)[1]]
    assert missing == [], missing


# ---- the Windows failure itself, on any computer ------------------------------------------------------------

def _texts():
    for j in jurisdictions():
        yield from sorted(j.rglob("*.yaml")) + sorted((j / "2_extracted_text").glob("*.jsonl"))


def test_the_law_reads_wrongly_as_cp1252_which_is_what_windows_did():
    """The original failure, pinned: the definitions file read as Windows' cp1252 shows "â€”" where the city wrote
    "—", and some extracted text can't be read as cp1252 at all. So the encoding is load-bearing, not tidiness."""
    j = REPO / "regulations/jurisdictions/new_york/ithaca_city"
    raw = (j / "4_term_definitions/definitions.yaml").read_bytes()
    assert "GRADE PLANE —" in raw.decode("utf-8")
    assert "GRADE PLANE â€”" in raw.decode("cp1252", errors="replace")                 # the mojibake from the bug
    unreadable = []
    for p in (j / "2_extracted_text").glob("*.jsonl"):
        try:
            p.read_bytes().decode("cp1252")
        except UnicodeDecodeError:
            unreadable.append(p.name)
    assert unreadable, "some extracted text holds bytes cp1252 can't decode (0x9d)"


# A fresh Python that, like Windows, reads any file not given an encoding as cp1252: open() and io.open (which
# Path.open, read_text and write_text use) get cp1252 whenever the caller names no encoding.
AS_WINDOWS = """
import builtins, io, runpy, sys
real = io.open
def windows_open(file, mode="r", buffering=-1, encoding=None, *args, **kwargs):
    if "b" not in mode and encoding in (None, "locale"):     # pathlib passes "locale" for none
        encoding = "cp1252"
    return real(file, mode, buffering, encoding, *args, **kwargs)
builtins.open = io.open = windows_open
assert open(sys.argv[1]).encoding == "cp1252"
sys.argv = [sys.argv[2]]
runpy.run_module(sys.argv[0], run_name="__main__")
"""


def _as_windows(module):
    """Its output goes to a cp1252 pipe too, as a Windows command's sent to a file or CI (✓ can't be printed there)."""
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    env["PYTHONIOENCODING"] = "cp1252"
    return subprocess.run([sys.executable, "-X", "utf8=0", "-c", AS_WINDOWS, str(REPO / "pyproject.toml"), module],
                          cwd=REPO, env=env, capture_output=True, text=True, encoding="utf-8", timeout=600)


def test_rule_format_passes_when_the_computer_reads_cp1252():
    """The bug on Windows, reproduced on any computer: before the fix this failed with "definitions.yaml:
    grade_plane: ... quote isn't at lines 32-33; not on this page: 'GRADE PLANE â€”'"."""
    done = _as_windows("rule_format")
    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-3000:]


def test_the_scenarios_command_prints_on_a_cp1252_pipe():
    """Review round 1: `python -m design_checker.scenarios` printed its table without utf8_console and crashed."""
    done = _as_windows("design_checker.scenarios")
    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-3000:]
    assert "disagreement(s)" in done.stdout


def test_the_cp1252_probe_really_breaks_code_that_names_no_encoding(tmp_path):
    """The probe above is only proof if it reproduces the failure: a reader without an encoding gets "â€”"."""
    (tmp_path / "law.txt").write_bytes("GRADE PLANE — A reference plane".encode("utf-8"))
    (tmp_path / "reader.py").write_text("import pathlib, sys\n"
                                        "print(ascii(pathlib.Path(sys.argv[1]).read_text()))\n", encoding="utf-8")
    probe = AS_WINDOWS.replace("sys.argv = [sys.argv[2]]", "sys.argv = [sys.argv[2], %r]" % str(tmp_path / "law.txt"))
    probe = probe.replace('runpy.run_module(sys.argv[0], run_name="__main__")',
                          'runpy.run_path(%r, run_name="__main__")' % str(tmp_path / "reader.py"))
    done = subprocess.run([sys.executable, "-c", probe, str(REPO / "pyproject.toml"), "reader"],
                          capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert "\\xe2\\u20ac\\u201d" in done.stdout, done.stdout + done.stderr      # "â€”", as on Windows
