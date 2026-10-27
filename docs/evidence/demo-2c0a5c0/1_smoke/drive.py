"""Run the demo smoke in Rhino (phase run, then close), capturing Rhino's own windows by id after the run."""
import json
import os
import shutil
import subprocess
import sys
import time

S = "/private/tmp/claude-501/-Users-benzhao-Documents-Gordium/bdb07cc0-1635-44d8-9b5a-34b881c6c09f/scratchpad"
PY = "/Users/benzhao/Documents/Gordium/.venv/bin/python"
RC = "/private/tmp/claude-501/-Users-benzhao-Documents-Gordium/624e933b-7d2e-463f-9744-6e95edbe5cbe/scratchpad/laneC/tools/rc.py"
HERE = "/private/tmp/claude-501/-Users-benzhao-Documents-Gordium/624e933b-7d2e-463f-9744-6e95edbe5cbe/scratchpad/demo6_runs/smoke/"
T = "/var/folders/v8/d2m6h2cn6s79xn6mrv2d8cr80000gn/T/gordium_demo_smoke/"


def windows():
    rows = subprocess.run(["/private/tmp/claude-501/-Users-benzhao-Documents-Gordium/624e933b-7d2e-463f-9744-6e95edbe5cbe/scratchpad/laneC/tools/rhino_windows_bin"], capture_output=True, text=True).stdout
    return [(int(r.split("\t")[0]), r.split("\t")[1]) for r in rows.splitlines() if "\t" in r]


def step(phase):
    open(HERE + "pre.py", "w").write("import scriptcontext as sc\nsc.sticky['demo_smoke_phase'] = %r\n" % phase)
    subprocess.run([PY, RC, "script", HERE + "pre.py"], check=True)
    time.sleep(1)
    if os.path.exists(T + "ready.json"):
        os.remove(T + "ready.json")
    start = time.time()
    subprocess.run([PY, RC, "script", HERE + "smoke.py"], check=True)
    while time.time() - start < 300 and not os.path.exists(T + "ready.json"):
        time.sleep(0.5)
    time.sleep(2.5)
    return json.load(open(T + phase + ".json", encoding="utf-8"))


run = step("run")
wins = windows()
for wid in sorted((i for i, t in wins if "demo_smoke" in t), reverse=True):
    if subprocess.run(["screencapture", "-x", "-o", "-l%d" % wid, HERE + "3_document.png"]).returncode == 0:
        break
for wid in sorted((i for i, t in wins if t == "TabPanelDockBarFloatingForm()"), reverse=True):
    if subprocess.run(["screencapture", "-x", "-o", "-l%d" % wid, HERE + "4_panel.png"]).returncode == 0:
        break
for f in os.listdir(T):
    if f.endswith("_view.png"):
        shutil.copy(T + f, HERE + f)
shutil.copy(T + "run.json", HERE + "run.json")
closed = step("close")
print(json.dumps({k: v["ok"] for k, v in run["claims"].items()}, indent=1))
print("ok:", run.get("ok"), "| trace:", (run.get("trace") or "")[-500:])
print("front:", run.get("front"))
print("report:", run.get("report"))
print("closed:", closed.get("closed"), closed.get("trace"))
