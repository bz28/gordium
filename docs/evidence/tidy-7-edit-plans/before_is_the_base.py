"""Tidy-up PR 7: the BEFORE copy in packages/design_checker/tests/test_edit_plans.py is apply_lookup and apply_reset
exactly as the base branch had them (character for character), so the before/after tests compare against the real
old code, not a retyped one.

Usage (from the repo root): python docs/evidence/tidy-7-edit-plans/before_is_the_base.py [base]
(base: default origin/tidy-6-host-core-move-2)"""
import ast
import subprocess
import sys

BASE = sys.argv[1] if len(sys.argv) > 1 else "origin/tidy-6-host-core-move-2"


def show(path):
    return subprocess.run(["git", "show", BASE + ":" + path], capture_output=True, text=True, encoding="utf-8",
                          check=True).stdout


def function(source, name):
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return "\n".join(source.splitlines()[node.lineno - 1:node.end_lineno])


test = open("packages/design_checker/tests/test_edit_plans.py", encoding="utf-8").read()
before = ast.literal_eval(next(n.value for n in ast.parse(test).body if isinstance(n, ast.Assign)
                               and getattr(n.targets[0], "id", "") == "BEFORE"))
base = {"apply_lookup": function(show("packages/design_checker/design_checker/host_core/edits.py"), "apply_lookup"),
        "apply_reset": function(show("packages/design_checker/design_checker/rhino_logic.py"), "apply_reset")}
ok = True
for name, text in base.items():
    copied = function(before, name)
    same = copied == text
    ok &= same
    print("%s: %d lines, %s" % (name, len(text.splitlines()), "identical to " + BASE if same else "DIFFERENT"))
print("OK: BEFORE is the base's code" if ok else "FAILED")
sys.exit(0 if ok else 1)
