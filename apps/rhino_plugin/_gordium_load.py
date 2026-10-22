"""Load this copy's Gordium into Rhino's Python for a command (GordiumStart, GordiumCheck, …).

Rhino keeps one Python session, so a module loaded from another copy of the repository (a test run, another
checkout) would otherwise keep answering: its code, its remembered repository folder and its background worker.
When the loaded Gordium isn't this folder's, it is switched off and forgotten (the same steps the in-Rhino tests
take before each run), and this folder's is loaded. The display conduit delegates to module functions, so a fresh
module is safe to load in the same session."""
import os
import sys

MODULES = ("gordium_rhino", "gordium_ui", "rhino_logic")


def module(here):
    import scriptcontext as sc
    here = os.path.abspath(here)
    loaded = sys.modules.get("gordium_rhino")
    if loaded is not None and os.path.dirname(os.path.abspath(loaded.__file__)) != here:
        try:
            loaded.off()                     # its drawing and hooks off, its panel closed
        except Exception:
            pass
        state = sc.sticky.get("gordium_state") or {}
        worker = state.pop("worker", None)
        if worker is not None:
            try:
                worker.terminate()
            except Exception:
                pass
        state.clear()                        # the other copy's repository folder, paths and choices
        for name in MODULES:
            sys.modules.pop(name, None)
        repo = os.path.dirname(os.path.dirname(here))
        sys.path[:] = [p for p in sys.path if not (p.endswith(os.path.join("apps", "rhino_plugin")) or
                                                    p.endswith(os.path.join("design_checker", "design_checker")))
                       or p.startswith(repo)]
    if here in sys.path:
        sys.path.remove(here)
    sys.path.insert(0, here)
    import gordium_rhino
    return gordium_rhino
