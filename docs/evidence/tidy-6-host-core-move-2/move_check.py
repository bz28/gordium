"""Proof that tidy-up PR 6 only MOVES code: every top-level statement of PR 5's rhino_logic.py (after its facade) is
in exactly one of the new files (rhino_logic.py or one of the six new host_core modules), byte-for-byte and with an
identical syntax tree, in the same order; the new files add nothing else except imports, `__all__`, docstrings and
rhino_logic's facade block; and PR 5's own host_core modules are unchanged.

    python move_check.py <base git ref>        (run from the repository root; the base is tidy-5-host-core-move)
"""
import ast
import subprocess
import sys
from collections import Counter
from pathlib import Path

DC = "packages/design_checker/design_checker"
NEW = ("freshness", "report", "panel_words", "context", "edits", "worker_client")
OLD = ("place", "streets", "facts", "lookup", "start_box")
NEW_FILES = [f"{DC}/rhino_logic.py"] + [f"{DC}/host_core/{m}.py" for m in NEW]


def names_of(n):
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return (n.name,)
    if isinstance(n, ast.Assign):
        out = []
        for t in n.targets:
            out += [t.id] if isinstance(t, ast.Name) else [e.id for e in getattr(t, "elts", [])
                                                           if isinstance(e, ast.Name)]
        return tuple(out)
    return ()


def statements(src):
    out = []
    for n in ast.parse(src).body:
        if isinstance(n, (ast.Import, ast.ImportFrom)) or (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)):
            out.append((None, n, None))
            continue
        out.append((names_of(n), n, ast.get_source_segment(src, n)))
    return out


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def main(base):
    problems, extra = [], []
    # PR 5's modules: not one byte changed
    for m in OLD:
        if git("diff", base, "--", f"{DC}/host_core/{m}.py"):
            problems.append(f"host_core/{m}.py changed (PR 5's module: this PR only adds modules)")
    old_src = git("show", f"{base}:{DC}/rhino_logic.py")
    old_all = statements(old_src)
    start = next(i for i, (k, n, t) in enumerate(old_all) if k == ("LAYERS",))
    old = [(k, n, t) for k, n, t in old_all[start:] if k is not None]
    facade_lines = old_src.splitlines()[:old_all[start][1].lineno - 1]      # PR 5's docstring, imports and facade
    where = {}
    new_rhino = statements(Path(NEW_FILES[0]).read_text(encoding="utf-8"))
    facade_end = next(i for i, (k, n, t) in enumerate(new_rhino) if k == ("LAYERS",))
    for path in NEW_FILES:
        src = Path(path).read_text(encoding="utf-8")
        for pos, (k, n, t) in enumerate(statements(src)):
            if k is None:
                continue
            if k == ("__all__",) or (path.endswith("rhino_logic.py") and pos < facade_end):
                extra.append((path, k or ast.unparse(n)[:40]))
                continue
            if not k:
                problems.append(f"{path}: a new statement that is not an import: {ast.unparse(n)[:80]}")
                continue
            if k in where:
                problems.append(f"{k} is in two files: {where[k][0]} and {path}")
            where[k] = (path, pos, n, t)
    order, same_tree, same_bytes = {}, 0, 0
    for k, n, t in old:
        if k not in where:
            problems.append(f"{k} is missing from every new file")
            continue
        path, pos, n2, t2 = where.pop(k)
        if order.get(path, -1) > pos:
            problems.append(f"{k} is out of order in {path}")
        order[path] = pos
        same_tree += ast.dump(n2) == ast.dump(n)
        same_bytes += t2 == t
        if ast.dump(n2) != ast.dump(n):
            problems.append(f"{k}: its syntax tree changed")
        if t2 != t:
            problems.append(f"{k}: its text changed")
    for k, (path, *_rest) in where.items():
        problems.append(f"{k} in {path} is new (not in {base})")
    # ...and every line after the old facade, comments included, is in a new file (as many times)
    body_lines = old_src.splitlines()[len(facade_lines):]
    new_lines = Counter(line for path in NEW_FILES for line in Path(path).read_text(encoding="utf-8").splitlines())
    lost = Counter(line for line in body_lines if line.strip()) - new_lines
    for line, count in lost.items():
        problems.append(f"a line of the old file is not in any new file ({count}x): {line.strip()[:80]}")
    print(f"{len(old)} top-level statements after the facade in {base}'s rhino_logic.py; {same_tree} with an "
          f"identical syntax tree, {same_bytes} byte-identical")
    print("added (not code):", ", ".join(f"{Path(p).name}:{'/'.join(k) if isinstance(k, tuple) else k}"
                                         for p, k in extra))
    print(f"PR 5's modules unchanged: {', '.join(OLD)}")
    for p in problems:
        print("PROBLEM:", p)
    if not lost:
        print(f"every one of the old file's {sum(1 for x in body_lines if x.strip())} non-blank lines after its "
              f"facade (comments included) is in a new file")
    print("OK: move only" if not problems else f"FAILED: {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
