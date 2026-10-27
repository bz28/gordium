#! python3
import json, os, sys, tempfile, time
import Rhino, Rhino.Geometry as rg, scriptcontext as sc, System
X = sys.argv[1] if False else open("/private/tmp/claude-501/-Users-benzhao-Documents-Gordium/624e933b-7d2e-463f-9744-6e95edbe5cbe/scratchpad/laneC2/real/head.txt").read().strip()
tests = X + "/apps/rhino_plugin/tests"
sys.path.insert(0, tests)
from test_docs_in_rhino import TestDocs
app = X + "/apps/rhino_plugin"
for m in [k for k in sys.modules if k.startswith("gordium") or k == "rhino_logic"]:
    sys.modules.pop(m)
sys.path.insert(0, app)
sys.path.insert(0, X + "/packages/design_checker/design_checker")
import gordium_rhino as g
sc.sticky.setdefault("gordium_state", {})
doc = TestDocs("real").__enter__().open("Large Objects - Feet")
g.gordium_check()
out = {"doc": doc.Name, "objs": doc.Objects.Count}
json.dump(out, open(os.path.join(tempfile.gettempdir(), "real_setup.json"), "w"))
