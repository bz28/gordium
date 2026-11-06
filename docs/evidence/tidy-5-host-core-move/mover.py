"""How tidy-up PR 5's files were made: host_core/*.py and the rhino_logic.py facade, generated from the base
rhino_logic.py by cutting whole top-level statements (with the comment lines above them) and pasting them, in their
original order, into their new module. Nothing inside a statement is retyped; the only edits are the two file paths
worked out from a file's own folder (EDITS), now one folder deeper. move_check.py proves the result.

    git show tidy-2-host-source:packages/design_checker/design_checker/rhino_logic.py > /tmp/base.py
    python mover.py /tmp/base.py where_each_name_goes.json packages/design_checker/design_checker

where_each_name_goes.json: each top-level name -> its module ("rhino" stays in rhino_logic.py). It is the plan's
table (tidy_up_plan_2026-11-02.md, section 2), matched by name, plus the few names the plan's line ranges missed
that the moved code needs (see the PR)."""
import ast
import json
import sys
from pathlib import Path

base_src, home_json, out_dir = sys.argv[1], sys.argv[2], Path(sys.argv[3])
src = Path(base_src).read_text(encoding="utf-8")
lines = src.splitlines(keepends=True)
tree = ast.parse(src)
home = json.load(open(home_json))
STDLIB = {"contextlib": "import contextlib", "_dt": "import datetime as _dt", "json": "import json",
          "math": "import math", "os": "import os", "queue": "import queue", "re": "import re",
          "threading": "import threading", "time": "import time"}
ORDER = ["place", "streets", "facts", "lookup", "start_box"]
DOCS = {
    "place": "The place the checker works for (its name, its address words, its time zone), read from place.json.",
    "streets": "Which edges of the lot face a street: picking them, naming them, and the one-street-or-two verdict.",
    "facts": "The facts about a site the architect states (use, stories, corner lot, ground...): which are needed,\n"
             "what each answer means, where each came from, and the use questions and row dialog that ask for them.",
    "lookup": "The address lookup's answer turned into the start box's choices, and the saved and typed addresses.",
    "start_box": "The start box: its rows, its buttons and what they say, when Draw is on, a lookup's preview,\n"
                 "and starting again.",
}


def names_of(n):
    if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
        return [n.name]
    if isinstance(n, ast.Assign):
        out = []
        for t in n.targets:
            out += [t.id] if isinstance(t, ast.Name) else [e.id for e in t.elts]
        return out
    if isinstance(n, ast.With):
        return ["PLACE"]
    return []


body = tree.body
first = next(i for i, n in enumerate(body) if not isinstance(n, (ast.Import, ast.Expr)))
header = "".join(lines[:body[first - 1].end_lineno])
header = header.replace("import re\n", "import re\nimport sys\n").replace("import time\n", "import time\nimport types\n")
header = header.replace("import datetime as _dt\n", "")       # only city_day used it, and it moved (start_box)
segments = []        # (home, names, text, node)
prev_end = body[first - 1].end_lineno
for n in body[first:]:
    ns = names_of(n)
    assert ns, ast.dump(n)[:80]
    homes = {home[x] for x in ns}
    assert len(homes) == 1, ns
    text = "".join(lines[prev_end:n.end_lineno])
    segments.append((homes.pop(), ns, text, n))
    prev_end = n.end_lineno
assert prev_end == len(lines)

own = {m: [x for h, ns, _, _ in segments if h == m for x in ns] for m in ORDER}
import symtable


def global_names(table):
    """Every name a scope (and the scopes inside it) reads from the module, from Python's own symbol table."""
    out = {s.get_name() for s in table.get_symbols() if s.is_referenced() and s.is_global()}
    for child in table.get_children():
        out |= global_names(child)
    return out


top_table = symtable.symtable(src, base_src, "exec")
scopes = {}
for child in top_table.get_children():
    scopes.setdefault(child.get_name(), []).append(child)
used = {m: set() for m in ORDER}
for h, ns, _, n in segments:
    if h in used:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            # what the definition itself evaluates (defaults, decorators, bases) is read at module level
            outer = n.args.defaults + [d for d in n.args.kw_defaults if d] + n.decorator_list if isinstance(
                n, ast.FunctionDef) else n.bases + n.decorator_list
            used[h] |= {x.id for e in outer for x in ast.walk(e) if isinstance(x, ast.Name)}
            (table,) = scopes[n.name]
            used[h] |= global_names(table)
        else:   # a module-level statement: every name it reads (a comprehension's own names are its own scope)
            used[h] |= {x.id for x in ast.walk(n) if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load)}


import textwrap


def wrapped(head, items, tail=""):
    """`head` + the items joined by ", ", wrapped at 120 columns inside parentheses or brackets."""
    one = head + ", ".join(items) + tail
    if len(one) <= 120:
        return one
    return "\n".join(textwrap.wrap(one, 120, subsequent_indent=" " * 4, break_long_words=False,
                                    break_on_hyphens=False))


# the only lines that change: file paths that are worked out from this file's own folder, now one folder deeper
EDITS = {
    "place": [('os.path.join(os.path.dirname(os.path.abspath(__file__)), "place.json")',
               'os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "place.json")'),
              ("# place.json beside this file by", "# place.json one folder up by")],
    "streets": [('"..", "..", "model_measurement",\n', '"..", "..", "..", "model_measurement",\n')],
}


def import_line(mod, names, noqa=""):
    one = f"from .{mod} import " + ", ".join(names) + noqa
    if len(one) <= 120:
        return one + "\n"
    body = textwrap.wrap(", ".join(names), 116, initial_indent="    ", subsequent_indent="    ",
                         break_long_words=False, break_on_hyphens=False)
    return f"from .{mod} import (" + noqa + "\n" + "\n".join(body) + ")\n"


def strip_lead(text):
    return text.lstrip("\n")


for m in ORDER:
    parts = ['"""' + DOCS[m] + '\n\nMoved here unchanged from rhino_logic.py, which still offers every name (so the Rhino plugin is\n'
             'unchanged). Python 3.9 and the standard library only: Rhino 8 imports this into its own Python 3.9,\n'
             'where none of the .venv\'s packages are installed."""\n\n']
    imps = [STDLIB[k] for k in STDLIB if k in used[m]]
    if imps:
        parts.append("\n".join(imps) + "\n")
    early, late = {}, {}
    for x in sorted(used[m]):
        hx = home.get(x)
        if hx in (None, "rhino", m):
            assert hx != "rhino", (m, x)
            continue
        (early if hx in ("place", "streets") else late).setdefault(hx, []).append(x)
    for hx in ORDER:
        if hx in early:
            parts.append(import_line(hx, early[hx]))
    parts.append("\n" + wrapped("__all__ = [", [repr(x) for x in own[m]], "]") + "\n")
    segs = [t for h, _, t, _ in segments if h == m]
    segs[0] = "\n\n" + strip_lead(segs[0])
    parts += segs
    if late:
        parts.append("\n\n# Names these functions call from the host_core modules that call back into this one. They are\n"
                     "# imported last, after every definition above, so the modules load in any order.\n")
        for hx in ORDER:
            if hx in late:
                parts.append(import_line(hx, late[hx], "  # noqa: E402"))
    text = "".join(parts)
    for old, new in EDITS.get(m, []):
        assert text.count(old) == 1, (m, old)
        text = text.replace(old, new)
    (out_dir / "host_core" / f"{m}.py").write_text(text, encoding="utf-8")

# the facade
rest = [t for h, _, t, _ in segments if h == "rhino"]
moved = [x for m in ORDER for x in own[m]]
facade = '''
# Host-neutral code lives in host_core/ (facts, streets, lookup, the start box, the place), moved there unchanged
# so a second host (a Revit add-in) can use it too. Every moved name is still offered here, the very same object
# (logic.X is host_core.<module>.X), so the Rhino plugin and its tests are unchanged.
if __package__:              # design_checker.rhino_logic: the checker, the tests
    from .host_core import facts as _facts, lookup as _lookup, place as _place, start_box as _start_box
    from .host_core import streets as _streets
else:                        # Rhino: this file by its folder on sys.path (gordium_rhino.py), so host_core is beside it
    for _name in [n for n in sys.modules if n == "host_core" or n.startswith("host_core.")]:
        del sys.modules[_name]           # a copy loaded before (another checkout, an older load): this folder's
    from host_core import facts as _facts, lookup as _lookup, place as _place, start_box as _start_box
    from host_core import streets as _streets
HOST_CORE = (_place, _streets, _facts, _lookup, _start_box)
MOVED = {name: module for module in HOST_CORE for name in module.__all__}   # name -> the module that defines it
globals().update({name: getattr(module, name) for name, module in MOVED.items()})


class _Facade(types.ModuleType):
    """This module, refusing to rebind a moved name: `logic.X = ...` (or monkeypatch.setattr(logic, "X", ...))
    would change only this module's copy, never the one host_core's own functions read, so the change would
    silently do nothing. Patch the name where it is defined (MOVED[name]) and in every module that imports it."""

    def __setattr__(self, name, value):
        if name in MOVED:
            raise AttributeError("%s moved to %s: set it there, not on rhino_logic" % (name, MOVED[name].__name__))
        super().__setattr__(name, value)

    def __delattr__(self, name):
        if name in MOVED:
            raise AttributeError("%s moved to %s: delete it there, not on rhino_logic" % (name, MOVED[name].__name__))
        super().__delattr__(name)


if __name__ in sys.modules:          # imported (not run from a file by a loader that keeps it to itself)
    sys.modules[__name__].__class__ = _Facade
'''
rest[0] = "\n" + rest[0]
(out_dir / "rhino_logic.py").write_text(header + facade + "".join(rest), encoding="utf-8")
print({m: len(own[m]) for m in ORDER}, "stay:", sum(len(ns) for h, ns, _, _ in segments if h == "rhino"))
