"""The in-Rhino test scripts (apps/rhino_plugin/tests/*_in_rhino.py) replace the plugin's own prompts and dialogs
with stand-ins (`g._pick = …`, `g.ui.row_dialog = …`), since a script can't type at Rhino's prompt or in a modal
dialog. A stand-in for a function the plugin no longer has is silently never called: the real prompt or dialog
then blocks the run, or the claim tests nothing (needs_in_rhino and undo_steps_in_rhino still replaced the removed
`_count` and `_ask_yes_no_or_skip` after the row's dialog took their place: Rhino job handover, 2026-10-28). Run in
CI, no Rhino: every name a script assigns on the plugin is one its module really defines."""
import ast

from rule_format.rulebook import REPO
from host_source import host_path, host_scripts, host_text_of



def _defined(path):
    """The names a module defines at its top level: functions, classes, assignments and imports, including those
    inside a top-level if / try / with / for (never inside a function or class)."""
    names, todo = set(), list(ast.parse(host_text_of(path, purpose="wiring")).body)
    while todo:
        node = todo.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
            continue
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.For, ast.With)):
            for t in (node.targets if isinstance(node, ast.Assign) else
                      [node.target] if not isinstance(node, ast.With) else
                      [i.optional_vars for i in node.items if i.optional_vars is not None]):
                names.update(n.id for n in ast.walk(t) if isinstance(n, ast.Name))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update((a.asname or a.name).split(".")[0] for a in node.names)
        for field in ("body", "orelse", "finalbody", "handlers"):
            todo.extend(getattr(node, field, None) or [])
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
    """Every (owner, name) a script sets on the plugin: `g.X = …`, `g.ui.X, g._y = …`, `setattr(g.ui, "X", …)`."""
    out = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            for t in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                for part in (t.elts if isinstance(t, ast.Tuple) else [t]):
                    found = _owner(part)
                    if found:
                        out.append(found)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "setattr" and \
                len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
            found = _owner(ast.Attribute(value=node.args[0], attr=node.args[1].value))
            if found:
                out.append(found)
    return out


def test_every_stand_in_names_a_function_the_plugin_has():
    defined = {"g": _defined(host_path("rhino", "plugin")), "g.ui": _defined(host_path("rhino", "ui")),
               "g.logic": _defined(host_path("rhino", "logic"))}
    stale, seen = [], 0
    for script in host_scripts("rhino"):
        for owner, name in stand_ins(host_text_of(script, purpose="wiring")):
            seen += 1
            if name not in defined[owner]:
                stale.append(f"{script.name}: {owner}.{name}")
    assert seen >= 20                          # the scripts do replace things (the check reads them)
    assert stale == []


def test_a_removed_name_is_caught():
    """The check itself: the stand-ins the row's dialog replaced are caught."""
    defined = _defined(host_path("rhino", "plugin"))
    old = stand_ins("g._count = lambda prompt: 2\ng._ask_yes_no_or_skip, g._pick = a, b\n")
    assert old == [("g", "_count"), ("g", "_ask_yes_no_or_skip"), ("g", "_pick")]
    assert [n for _, n in old if n not in defined] == ["_count", "_ask_yes_no_or_skip"]
    assert stand_ins("setattr(g.ui, 'row_dialog', f)\nsetattr(g, '_count', f)\n") == [("g.ui", "row_dialog"),
                                                                                    ("g", "_count")]


def test_a_name_defined_under_a_top_level_if_or_try_counts(tmp_path):
    """Review round 1: a name defined inside a top-level if / try (gordium_rhino has both) is the module's own."""
    mod = tmp_path / "m.py"
    mod.write_text("import os\nif os.sep:\n    def a(): pass\ntry:\n    B = 1\nexcept Exception:\n    def c(): pass\n"
                   "def d():\n    hidden = 1\n", encoding="utf-8")
    assert _defined(mod) == {"os", "a", "B", "c", "d"}
