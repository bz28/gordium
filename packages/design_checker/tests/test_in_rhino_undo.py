"""The in-Rhino test scripts (apps/rhino_plugin/tests/*_in_rhino.py) undo and redo with Rhino's own commands run in
the document (RhinoApp.ExecuteCommand(doc, "_Undo")), never with RhinoDoc.Undo() or RhinoDoc.Redo(): called from a
script those open an undo record they never end and drop the step they undid, so a Redo finds nothing
(side_yards_in_rhino's "Redo brings the new house back" failed that way on every branch while Gordium's Redo worked,
2026-11-12; shown with a plain curve and no Gordium code loaded). Nor with RhinoApp.RunScript("_Undo"), which does
nothing while no Rhino window is on screen (undo_steps_in_rhino's "undone" claims all failed that way, 2026-10-28).
Run in CI, no Rhino."""
import ast

from host_source import host_scripts, host_tree

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


def _run_script_undo_calls(source):
    """Each line that calls RunScript with "_Undo" or "_Redo" written in its command."""
    return [node.lineno for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "RunScript"
            and node.args and any(isinstance(c, ast.Constant) and isinstance(c.value, str) and
                                  any(w in c.value for w in ("_Undo", "_Redo")) for c in ast.walk(node.args[0]))]


def test_no_in_rhino_script_undoes_with_rhinodoc_undo():
    scripts = host_scripts("rhino")
    assert scripts
    bad = {p.name: lines for p in scripts if (lines := _doc_undo_calls(p.read_text(encoding="utf-8")))}
    assert not bad, bad


def test_no_in_rhino_script_undoes_with_run_script():
    scripts = sorted(p for p in host_tree("rhino") if "_in_rhino" in p.name)
    bad = {p.name: lines for p in scripts if (lines := _run_script_undo_calls(p.read_text(encoding="utf-8")))}
    assert not bad, bad


def test_the_run_script_check_catches_it():
    assert _run_script_undo_calls('Rhino.RhinoApp.RunScript("_Undo", False)\n') == [1]
    assert _run_script_undo_calls('x = 1\nbool(Rhino.RhinoApp.RunScript("_Redo", False))\n') == [2]
    assert _run_script_undo_calls('Rhino.RhinoApp.RunScript("_Line 0,0,0 1,0,0", False)\n') == []
    assert _run_script_undo_calls('Rhino.RhinoApp.ExecuteCommand(doc, "_Undo")\n') == []


def test_the_check_catches_both_ways_of_calling_it():
    assert _doc_undo_calls("doc.Undo()\n") == [1]
    assert _doc_undo_calls('x = 1\nfn = getattr(doc, "Redo" if redo else "Undo", None)\n') == [2]
    assert _doc_undo_calls('Rhino.RhinoApp.ExecuteCommand(doc, "_Undo")\n') == []
