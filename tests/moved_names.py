"""How a test swaps a name that rhino_logic.py offers but host_core/ defines (FLAT_GROUND, STATED_FACTS, box_rows...).

Before the move, every function read such a name from one place, rhino_logic's own globals, so
`monkeypatch.setattr(logic, "FLAT_GROUND", False)` reached them all. Now the name is bound in several modules: the
one that defines it, each host_core module that imports it, and rhino_logic (which re-exports it, for the Rhino
plugin and for code that still lives there). A swap in only one of them would leave the others reading the old
value, and the test would pass for the wrong reason, so rhino_logic refuses `logic.X = ...` for a moved name and a
test calls `patch_moved` instead, which swaps every binding and lets monkeypatch put them all back afterwards.
"""

_UNSET = object()


def patch_moved(monkeypatch, logic, name, value):
    """Swap `name` for `value` in rhino_logic (`logic`, either copy: design_checker.rhino_logic or Rhino's plain
    rhino_logic) and in every host_core module that holds the same object, until the test ends."""
    old = getattr(logic.MOVED[name], name)
    for module in (logic, *logic.HOST_CORE):
        if vars(module).get(name, _UNSET) is old:
            monkeypatch.setitem(vars(module), name, value)     # the module's own dict: past rhino_logic's refusal
