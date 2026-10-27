import json, os, subprocess, sys, time
L = "/private/tmp/claude-501/-Users-benzhao-Documents-Gordium/624e933b-7d2e-463f-9744-6e95edbe5cbe/scratchpad/laneC/"
K = L + "run1/keys/"
def front():
    return subprocess.run(["osascript", "-e", 'tell application "System Events" to get name of first process whose frontmost is true'], capture_output=True, text=True).stdout.strip()
def key(code=None, text=None):
    f = front()
    if f != "Rhinoceros":
        raise SystemExit("ABORT: front app is %r, not Rhino; no key sent" % f)
    if text:
        subprocess.run(["osascript", "-e", 'tell application "System Events" to keystroke "%s"' % text])
    else:
        subprocess.run(["osascript", "-e", 'tell application "System Events" to key code %d' % code])
def cap(name):
    rows = subprocess.run([L + "tools/onscreen_bin"], capture_output=True, text=True).stdout
    ids = [int(r.split("\t")[0]) for r in rows.splitlines() if "blank_laneC" in r]
    if ids:
        subprocess.run(["screencapture", "-x", "-o", "-l%d" % max(ids), K + name + ".png"])
trials = {"enter_then_esc": [("k", 36), ("cap", "after_enter"), ("k", 53)],
          "no": [("t", "No"), ("k", 36)], "yes": [("t", "Yes"), ("k", 36)]}
res = {}
for t, steps in trials.items():
    open(L + "drivers/keys_pre.py", "w").write("import scriptcontext as sc\nsc.sticky['keys_trial'] = %r\n" % t)
    subprocess.run(["python3", L + "tools/rc.py", "script", L + "drivers/keys_pre.py"]); time.sleep(1)
    for f in ("waiting.txt", t + ".json"):
        if os.path.exists(K + f): os.remove(K + f)
    subprocess.run(["python3", L + "tools/rc.py", "script", L + "drivers/keys_trial.py"])
    end = time.time() + 30
    while time.time() < end and not os.path.exists(K + "waiting.txt"): time.sleep(0.3)
    time.sleep(1.5)
    for kind, v in steps:
        if kind == "k": key(code=v)
        elif kind == "t": key(text=v)
        else: cap(v)
        time.sleep(1.2)
    end = time.time() + 60
    while time.time() < end and not os.path.exists(K + t + ".json"): time.sleep(0.5)
    res[t] = json.load(open(K + t + ".json")) if os.path.exists(K + t + ".json") else "NO RESULT"
    print(t, json.dumps(res[t])[:700], flush=True)
