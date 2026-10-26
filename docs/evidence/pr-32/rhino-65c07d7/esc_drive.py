"""Runs esc_probe.py; once the wait window ("Gordium") is on screen, brings `front` (doc | wait) to the front,
captures the screen state, presses Esc once, and reports the probe's result. Usage: esc_drive.py <doc|wait>"""
import json
import os
import subprocess
import sys
import time

H = os.path.dirname(os.path.abspath(__file__)) + "/"
PY = "/Users/benzhao/Documents/Gordium/.venv/bin/python"
RC = H + "../rhino_mvp/tools/rc.py"
front = sys.argv[1]
open(H + "esc_mode.txt", "w", encoding="utf-8").write(front)
for f in ("esc_probe.json", "esc_waiting.json", "esc_raised.json"):
    if os.path.exists(H + f):
        os.remove(H + f)


def onscreen():
    rows = subprocess.run([H + "onscreen_bin"], capture_output=True, text=True).stdout.splitlines()
    return [r.split("\t") for r in rows if "\t" in r]


subprocess.run([PY, RC, "script", H + "esc_probe.py"], check=True)
t0 = time.time()
wait_win = None
while time.time() - t0 < 120:
    if os.path.exists(H + "esc_waiting.json"):
        wins = [w for w in onscreen() if w[1] == "Gordium"]
        if wins:
            wait_win = wins[0]
            break
    time.sleep(0.2)
log = {"front": front, "wait_window": wait_win}
if wait_win:
    subprocess.run(["osascript", "-e", 'tell application "Rhino 8" to activate'])   # keys go to the front app
    while time.time() - t0 < 120 and not os.path.exists(H + "esc_raised.json"):
        time.sleep(0.1)
    log["raised"] = json.load(open(H + "esc_raised.json", encoding="utf-8"))
    subprocess.run(["screencapture", "-x", "-o", "-l", wait_win[0], H + "esc_%s_wait_window.png" % front])
    log["esc_at"] = time.time()
    subprocess.run(["osascript", "-e", 'tell application "System Events" to key code 53'])
    time.sleep(1.5)
    log["after_1_5s"] = [w[1] for w in onscreen()]
while time.time() - t0 < 180 and not os.path.exists(H + "esc_probe.json"):
    time.sleep(0.3)
res = json.load(open(H + "esc_probe.json", encoding="utf-8")) if os.path.exists(H + "esc_probe.json") else None
log["probe"] = res
if res and wait_win:
    log["ended_after_esc_s"] = round(json.load(open(H + "esc_waiting.json"))["waiting_from"] + res["took_s"]
                                     - log["esc_at"], 2)
json.dump(log, open(H + "esc_drive_%s.json" % front, "w", encoding="utf-8"), indent=1, default=str)
print(json.dumps({k: v for k, v in log.items() if k != "probe"}, default=str))
print({k: res.get(k) for k in ("took_s", "cancelled", "result_none", "trace")} if res else "NO RESULT")
