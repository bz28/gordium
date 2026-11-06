"""Proof that tidy-up PR 5 only MOVES code: every top-level statement of the old rhino_logic.py is in exactly one of
the new files (rhino_logic.py or host_core/*.py), byte-for-byte and with an identical syntax tree, in the same
order; and the new files add nothing else except imports, `__all__`, docstrings and rhino_logic's facade block.
The two declared exceptions are the file paths worked out from a file's own folder, now one folder deeper.

    python move_check.py <base git ref>        (run from the repository root)
"""
import ast
import subprocess
import sys
from pathlib import Path

DC = "packages/design_checker/design_checker"
NEW_FILES = [f"{DC}/rhino_logic.py"] + [f"{DC}/host_core/{m}.py" for m in ("place", "streets", "facts", "lookup",
                                                                             "start_box")]
# name -> (old text, new text): the only changes allowed inside a moved statement
DECLARED = {
    "PLACE": ('os.path.join(os.path.dirname(os.path.abspath(__file__)), "place.json")',
              'os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "place.json")'),
    "_street_lines": ('"..", "..", "model_measurement",', '"..", "..", "..", "model_measurement",'),
}
COMMENTS = [("# place.json beside this file by", "# place.json one folder up by")]


def names_of(n):
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return (n.name,)
    if isinstance(n, ast.Assign):
        out = []
        for t in n.targets:
            out += [t.id] if isinstance(t, ast.Name) else [e.id for e in getattr(t, "elts", [])
                                                           if isinstance(e, ast.Name)]
        return tuple(out)
    if isinstance(n, ast.With):
        return tuple(x.id for s in n.body for t in getattr(s, "targets", []) for x in [t] if isinstance(x, ast.Name))
    return ()


def statements(src):
    tree = ast.parse(src)
    out = []
    for n in tree.body:
        if isinstance(n, (ast.Import, ast.ImportFrom)) or (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)):
            out.append((None, n, None))
            continue
        out.append((names_of(n), n, ast.get_source_segment(src, n)))
    return out


def main(base):
    old_src = subprocess.run(["git", "show", f"{base}:{DC}/rhino_logic.py"], capture_output=True, text=True,
                             check=True).stdout
    old = [(k, n, t) for k, n, t in statements(old_src) if k is not None]
    where = {}
    problems, extra = [], []
    first_kept = next(k for k, n, t in old if k == ("LAYERS",))
    facade_end = next(i for i, (k, n, t) in enumerate(statements(Path(NEW_FILES[0]).read_text(encoding="utf-8")))
                      if k == first_kept)
    for path in NEW_FILES:
        src = Path(path).read_text(encoding="utf-8")
        for pos, (k, n, t) in enumerate(statements(src)):
            if k is None:
                continue
            # the facade: rhino_logic's statements before its first old one (LAYERS), each one listed in the PR
            if k == ("__all__",) or (path.endswith("rhino_logic.py") and pos < facade_end):
                extra.append((path, k or ast.unparse(n)[:40]))
                continue
            if not k:
                problems.append(f"{path}: a new statement that is not an import: {ast.unparse(n)[:80]}")
                continue
            if k in where:
                problems.append(f"{k} is in two files: {where[k][0]} and {path}")
            where[k] = (path, pos, n, t)
    order = {}
    same_tree = same_bytes = 0
    for k, n, t in old:
        if k not in where:
            problems.append(f"{k} is missing from every new file")
            continue
        path, pos, n2, t2 = where.pop(k)
        if order.get(path, -1) > pos:
            problems.append(f"{k} is out of order in {path}")
        order[path] = pos
        expect_text, expect_tree = t, ast.dump(n)
        if k[0] in DECLARED:
            a, b = DECLARED[k[0]]
            assert t.count(a) == 1, k
            expect_text = t.replace(a, b)
            expect_tree = ast.dump(ast.parse(expect_text).body[0])
        same_tree += ast.dump(n2) == expect_tree
        same_bytes += t2 == expect_text
        if ast.dump(n2) != expect_tree:
            problems.append(f"{k}: its syntax tree changed")
        if t2 != expect_text:
            problems.append(f"{k}: its text changed")
    for k, (path, *_rest) in where.items():
        problems.append(f"{k} in {path} is new (not in {base})")
    # ...and every line of the old file, comments included, is in a new file (as many times), save the declared ones
    from collections import Counter
    new_lines = Counter(line for path in NEW_FILES for line in Path(path).read_text(encoding="utf-8").splitlines())
    for a, b in [*DECLARED.values(), *COMMENTS]:
        for line in old_src.splitlines():
            if a in line:
                new_lines[line] += 1
                new_lines[line.replace(a, b)] -= 1
    lost = Counter(line for line in old_src.splitlines() if line.strip()) - new_lines
    for line, count in lost.items():
        problems.append(f"a line of the old file is not in any new file ({count}x): {line.strip()[:80]}")
    print(f"{len(old)} top-level statements in {base}'s rhino_logic.py; {same_tree} with an identical syntax tree, "
          f"{same_bytes} byte-identical (each counting the {len(DECLARED)} declared path changes: "
          f"{', '.join(DECLARED)})")
    print("added (not code):", ", ".join(f"{Path(p).name}:{'/'.join(k) if isinstance(k, tuple) else k}"
                                         for p, k in extra))
    for p in problems:
        print("PROBLEM:", p)
    print(f"every one of the old file's {sum(1 for x in old_src.splitlines() if x.strip())} non-blank lines "
          f"(comments included) is in a new file" if not lost else "")
    print("OK: move only" if not problems else f"FAILED: {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
