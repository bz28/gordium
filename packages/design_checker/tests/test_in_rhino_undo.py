"""The in-Rhino test scripts (apps/rhino_plugin/tests/*_in_rhino.py) undo and redo with Rhino's own commands, never
with RhinoDoc.Undo() or RhinoDoc.Redo(). Called from a script those open an undo record they never end and drop the
step they undid, so a Redo finds nothing: side_yards_in_rhino's "Redo brings the new house back" failed that way on
every branch while Gordium's Redo worked (2026-11-12; shown with a plain curve and no Gordium code loaded). Run in
CI, no Rhino."""
import ast

from rule_format.rulebook import REPO

SCRIPTS = REPO / "apps/rhino_plugin/tests"
NAMES = {"Undo", "Redo"}


def _doc_undo_calls(source):
    """Each line that calls x.Undo() / x.Redo(), or reaches them by getattr(x, "Undo" …)."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr in NAMES:
            found.append(node.lineno)
        elif isinstance(f, ast.Name) and f.id == "getattr" and len(node.args) > 1 and any(
                isinstance(c, ast.Constant) and c.value in NAMES for c in ast.walk(node.args[1])):
            found.append(node.lineno)
    return found


def test_no_in_rhino_script_undoes_with_rhinodoc_undo():
    scripts = sorted(SCRIPTS.glob("*_in_rhino.py"))
    assert scripts
    bad = {p.name: lines for p in scripts if (lines := _doc_undo_calls(p.read_text(encoding="utf-8")))}
    assert not bad, bad


def test_the_check_catches_both_ways_of_calling_it():
    assert _doc_undo_calls("doc.Undo()\n") == [1]
    assert _doc_undo_calls('x = 1\nfn = getattr(doc, "Redo" if redo else "Undo", None)\n') == [2]
    assert _doc_undo_calls('Rhino.RhinoApp.ExecuteCommand(doc, "_Undo")\n') == []
