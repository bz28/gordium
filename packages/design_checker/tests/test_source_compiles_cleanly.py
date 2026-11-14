"""Every Python file in packages/ and apps/rhino_plugin compiles with no SyntaxWarning (an invalid escape such as
"\\(" in a normal string warns today and becomes an error in a later Python)."""
import warnings
from pathlib import Path
from host_source import host_tree

ROOT = Path(__file__).resolve().parents[3]


def test_no_python_file_raises_a_syntax_warning():
    files = sorted(p for p in [*(ROOT / "packages").rglob("*.py"), *host_tree("rhino")]
                   if not any(part.startswith(".") or part in ("build", "__pycache__")
                              for part in p.relative_to(ROOT).parts))
    assert len(files) > 50
    bad = []
    for path in files:
        with warnings.catch_warnings():
            warnings.simplefilter("error", SyntaxWarning)
            try:
                compile(path.read_text(encoding="utf-8"), str(path), "exec")
            except SyntaxError as e:                                   # a SyntaxWarning made an error
                bad.append(f"{path.relative_to(ROOT)}:{e.lineno}: {e.msg}")
    assert not bad, "\n".join(bad)
