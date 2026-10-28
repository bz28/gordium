"""The in-Rhino test scripts (apps/rhino_plugin/tests/*_in_rhino.py) replace the plugin's own prompts and dialogs
with stand-ins (`g._pick = …`, `g.ui.row_dialog = …`), since a script can't type at Rhino's prompt or in a modal
dialog. A stand-in for a function the plugin no longer has is silently never called: the real prompt or dialog
then blocks the run, or the claim tests nothing (needs_in_rhino and undo_steps_in_rhino still replaced the removed
`_count` and `_ask_yes_no_or_skip` after the row's dialog took their place: Rhino job handover, 2026-10-28). Run in
CI, no Rhino: every name a script assigns on the plugin is one its module really defines."""
import ast

from rule_format.rulebook import REPO

APP = REPO / "apps/rhino_plugin"


def _defined(path):
    """The names a module defines at its top level: functions, classes, assignments and imports."""
    names = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for t in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                names.update(n.id for n in ast.walk(t) if isinstance(n, ast.Name))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update((a.asname or a.name).split(".")[0] for a in node.names)
    return names


def _owner(node):
    """'g', 'g.ui' or 'g.logic' for a target g.X / g.ui.X / g.logic.X, and X; else None."""
    if not isinstance(node, ast.Attribute):
        return None
    base = node.value
    if isinstance(base, ast.Name) and base.id == "g":
        return "g", node.attr
    if isinstance(base, ast.Attribute) and isinstance(base.value, ast.Name) and base.value.id == "g" \
            and base.attr in ("ui", "logic"):
        return "g." + base.attr, node.attr
    return None


def stand_ins(text):
    """Every (owner, name) a script assigns on the plugin: `g.X = …`, `g.ui.X, g._y = …`."""
    out = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                for part in (t.elts if isinstance(t, ast.Tuple) else [t]):
                    found = _owner(part)
                    if found:
                        out.append(found)
    return out


def test_every_stand_in_names_a_function_the_plugin_has():
    logic = next(REPO.glob("packages/*/*/rhino_logic.py"))
    defined = {"g": _defined(APP / "gordium_rhino.py"), "g.ui": _defined(APP / "gordium_ui.py"),
               "g.logic": _defined(logic)}
    stale, seen = [], 0
    for script in sorted((APP / "tests").glob("*_in_rhino.py")):
        for owner, name in stand_ins(script.read_text(encoding="utf-8")):
            seen += 1
            if name not in defined[owner]:
                stale.append(f"{script.name}: {owner}.{name}")
    assert seen >= 20                          # the scripts do replace things (the check reads them)
    assert stale == []


def test_a_removed_name_is_caught():
    """The check itself: the stand-ins the row's dialog replaced are caught."""
    defined = _defined(APP / "gordium_rhino.py")
    old = stand_ins("g._count = lambda prompt: 2\ng._ask_yes_no_or_skip, g._pick = a, b\n")
    assert old == [("g", "_count"), ("g", "_ask_yes_no_or_skip"), ("g", "_pick")]
    assert [n for _, n in old if n not in defined] == ["_count", "_ask_yes_no_or_skip"]
