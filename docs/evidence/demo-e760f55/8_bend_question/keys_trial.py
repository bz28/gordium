#! python3
"""Keyboard check of the bend question: the plugin's own _ask_street_more with Rhino's real GetOption; keys are typed
by the driver (System Events) only while Rhino is frontmost. Records each prompt shown and the outcome."""
import json, sys, traceback, AppKit, Rhino, scriptcontext as sc
L = "/private/tmp/claude-501/-Users-benzhao-Documents-Gordium/624e933b-7d2e-463f-9744-6e95edbe5cbe/scratchpad/laneC/"
WT = L + "demo_e760f55"
trial = sc.sticky.get("keys_trial", "x")
out = {"trial": trial, "prompts": []}
try:
    app = WT + "/apps/rhino_plugin"
    if app not in sys.path:
        sys.path.insert(0, app)
    import gordium_rhino as g
    out["loaded_from"] = g.__file__
    class Rec(object):
        def __init__(self):
            self.go = Rhino.Input.Custom.GetOption()
        def SetCommandPrompt(self, t):
            out["prompts"].append(str(t)); self.go.SetCommandPrompt(t)
        def __getattr__(self, n):
            return getattr(self.go, n)
    class _C(object):
        def __getattr__(self, n):
            return Rec if n == "GetOption" else getattr(Rhino.Input.Custom, n)
    class _I(object):
        Custom = _C()
        def __getattr__(self, n):
            return getattr(Rhino.Input, n)
    class _R(object):
        Input = _I()
        def __getattr__(self, n):
            return getattr(Rhino, n)
    real = g.Rhino
    g.Rhino = _R()
    AppKit.NSApplication.SharedApplication.ActivateIgnoringOtherApps(True)
    d = Rhino.RhinoDoc.ActiveDoc
    w = Rhino.UI.RhinoEtoApp.MainWindowForDocument(d) if d else None
    if w is not None:
        w.BringToFront(); w.Focus()
    open(L + "run1/keys/waiting.txt", "w").write(trial)
    try:
        out["answer"] = g._ask_street_more("Past there the lot line turns 20° (a test). Is that on Street 2 too? (Yes or No)")
    except Exception as e:
        out["raised"] = type(e).__name__
    finally:
        g.Rhino = real
except Exception:
    out["trace"] = traceback.format_exc()
out["done"] = True
json.dump(out, open(L + "run1/keys/%s.json" % trial, "w"), indent=1)
