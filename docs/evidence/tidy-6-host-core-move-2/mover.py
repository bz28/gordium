"""How tidy-up PR 6's files were made: six more host_core modules (freshness, report, panel_words, context, edits,
worker_client) and the updated rhino_logic.py facade, generated from PR 5's rhino_logic.py by cutting whole
top-level statements (with the comment lines above them) and pasting them, in their original order, into their new
module. Nothing inside a statement is retyped. PR 5's five host_core modules are not touched. move_check.py proves
the result.

    git show tidy-5-host-core-move:packages/design_checker/design_checker/rhino_logic.py > /tmp/base.py
    python mover.py /tmp/base.py where_each_name_goes.json packages/design_checker/design_checker

where_each_name_goes.json: each top-level name still in PR 5's rhino_logic.py -> its module ("rhino" stays). It is
the plan's table (tidy_up_plan_2026-11-02.md, section 2), matched by name, plus the names the moved code needs and
minus the Rhino-only names the plan's line ranges caught (see the PR)."""
import ast
import json
import symtable
import sys
import textwrap
from pathlib import Path

base_src, home_json, out_dir = sys.argv[1], sys.argv[2], Path(sys.argv[3])
src = Path(base_src).read_text(encoding="utf-8")
lines = src.splitlines(keepends=True)
tree = ast.parse(src)
home = json.load(open(home_json))
OLD = ["place", "streets", "facts", "lookup", "start_box"]          # PR 5's modules (unchanged)
ORDER = ["freshness", "report", "panel_words", "context", "edits", "worker_client"]
for m in OLD:
    for x in ast.parse(Path(out_dir / "host_core" / f"{m}.py").read_text(encoding="utf-8")).body:
        if isinstance(x, ast.Assign) and getattr(x.targets[0], "id", None) == "__all__":
            for e in x.value.elts:
                home[e.value] = m
STDLIB = {"contextlib": "import contextlib", "json": "import json", "math": "import math", "os": "import os",
          "queue": "import queue", "re": "import re", "sys": "import sys", "threading": "import threading",
          "time": "import time", "types": "import types"}
DOCS = {
    "freshness": "Whether the results on screen are current: when the model counts as changed, when it is checked again,\n"
                 "what the panel says while the results are out of date (greyed), the undo steps' names, and the\n"
                 "panel's actions refused while a start box is open or Gordium is working.",
    "report": "What the panel says about the zoning report, and the words of long work: its steps, Cancel, and a model\n"
              "that changed while Gordium worked.",
    "panel_words": "The panel's words: its header, each row's name, status and details, the legend, the cells and links.",
    "context": "The neighbourhood drawn around a looked-up lot: when to draw it, what the file keeps of it, and how a\n"
               "new fetch merges with what is drawn.",
    "edits": "The start box's model edits as one transaction: Draw commits last, any other way out rolls back, and a\n"
             "lookup's answer is drawn through the session.",
    "worker_client": "The reference Python client of the checker (the worker): its two pipes, one request and its answer,\n"
                     "a long piece of work on its own thread, the session recorder, and when to restart the checker.",
}


def names_of(n):
    if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
        return [n.name]
    if isinstance(n, ast.Assign):
        out = []
        for t in n.targets:
            out += [t.id] if isinstance(t, ast.Name) else [e.id for e in t.elts]
        return out
    return []


body = tree.body
last_import = max(i for i, n in enumerate(body) if isinstance(n, ast.Import))
first = next(i for i, n in enumerate(body) if isinstance(n, ast.Assign) and names_of(n) == ["LAYERS"])
header_imports = body[1:last_import + 1]
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


def reads(n):
    if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
        # what the definition itself evaluates (defaults, decorators, bases) is read at module level
        outer = n.args.defaults + [d for d in n.args.kw_defaults if d] + n.decorator_list if isinstance(
            n, ast.FunctionDef) else n.bases + n.decorator_list
        got = {x.id for e in outer for x in ast.walk(e) if isinstance(x, ast.Name)}
        (table,) = scopes[n.name]
        return got | global_names(table)
    return {x.id for x in ast.walk(n) if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load)}


used = {m: set() for m in ORDER + ["rhino"]}
for h, ns, _, n in segments:
    used[h] |= reads(n)


def wrapped(head, items, tail=""):
    """`head` + the items joined by ", ", wrapped at 120 columns inside parentheses or brackets."""
    one = head + ", ".join(items) + tail
    if len(one) <= 120:
        return one
    return "\n".join(textwrap.wrap(one, 120, subsequent_indent=" " * 4, break_long_words=False,
                                    break_on_hyphens=False))


def import_line(mod, names, noqa=""):
    one = f"from .{mod} import " + ", ".join(names) + noqa
    if len(one) <= 120:
        return one + "\n"
    body = textwrap.wrap(", ".join(names), 116, initial_indent="    ", subsequent_indent="    ",
                         break_long_words=False, break_on_hyphens=False)
    return f"from .{mod} import (" + noqa + "\n" + "\n".join(body) + ")\n"


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
        if hx in (None, m):
            continue
        assert hx != "rhino", (m, x)           # host_core never imports from rhino_logic
        # PR 5's facts, lookup and start_box import each other at their ends; nothing imports these six modules
        # back, so each one's imports go at its top (late stays empty: kept for a later module that needs it)
        (early if hx in OLD + ORDER else late).setdefault(hx, []).append(x)
    for hx in OLD + ORDER:
        if hx in early:
            parts.append(import_line(hx, early[hx]))
    parts.append("\n" + wrapped("__all__ = [", [repr(x) for x in own[m]], "]") + "\n")
    segs = [t for h, _, t, _ in segments if h == m]
    segs[0] = "\n\n" + segs[0].lstrip("\n")
    parts += segs
    if late:
        parts.append("\n\n# Names these functions call from the host_core modules that call back into this one. They are\n"
                     "# imported last, after every definition above, so the modules load in any order.\n")
        for hx in OLD + ORDER:
            if hx in late:
                parts.append(import_line(hx, late[hx], "  # noqa: E402"))
    (out_dir / "host_core" / f"{m}.py").write_text("".join(parts), encoding="utf-8")

# rhino_logic: its docstring, the standard-library imports its remaining code (and the facade) still reads, the
# facade, then every statement that stays
rest = [t for h, _, t, _ in segments if h == "rhino"]
keep_used = used["rhino"] | {"sys", "types"}
docstring = "".join(lines[:body[0].end_lineno]) + "\n"
imports = "".join(ast.get_source_segment(src, n) + "\n" for n in header_imports
                  if (n.names[0].asname or n.names[0].name) in keep_used)
facade = '''
# Host-neutral code lives in host_core/ (facts, streets, lookup, the start box, the place, freshness, the report's
# and the panel's words, the neighbourhood, the box's edits, the worker client), moved there unchanged so a second
# host (a Revit add-in) can use it too. Every moved name is still offered here, the very same object
# (logic.X is host_core.<module>.X), so the Rhino plugin and its tests are unchanged.
if __package__:              # design_checker.rhino_logic: the checker, the tests
    from .host_core import facts as _facts, lookup as _lookup, place as _place, start_box as _start_box
    from .host_core import streets as _streets
    from .host_core import context as _context, edits as _edits, freshness as _freshness, report as _report
    from .host_core import panel_words as _panel_words, worker_client as _worker_client
else:                        # Rhino: this file by its folder on sys.path (gordium_rhino.py), so host_core is beside it
    for _name in [n for n in sys.modules if n == "host_core" or n.startswith("host_core.")]:
        del sys.modules[_name]           # a copy loaded before (another checkout, an older load): this folder's
    from host_core import facts as _facts, lookup as _lookup, place as _place, start_box as _start_box
    from host_core import streets as _streets
    from host_core import context as _context, edits as _edits, freshness as _freshness, report as _report
    from host_core import panel_words as _panel_words, worker_client as _worker_client
HOST_CORE = (_place, _streets, _facts, _lookup, _start_box, _freshness, _report, _panel_words, _context, _edits,
             _worker_client)
'''
old_facade = "".join(lines[header_imports[-1].end_lineno:body[first - 1].end_lineno])
tail = old_facade[old_facade.index("MOVED = {"):]          # MOVED, the re-export and _Facade: as they were
(out_dir / "rhino_logic.py").write_text(docstring + imports + facade + tail + "".join(rest), encoding="utf-8")
print({m: len(own[m]) for m in ORDER}, "stay:", sum(len(ns) for h, ns, _, _ in segments if h == "rhino"),
      "rhino imports:", [ast.get_source_segment(src, n) for n in header_imports
                         if (n.names[0].asname or n.names[0].name) in keep_used])
