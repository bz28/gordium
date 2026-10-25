"""Run a Python script in the running Rhino 8 (Rhino's own rhinocode tool), returning at once (the script may open
a modal box; the caller waits for the files it writes). Usage: rc.py script <path> | rc.py list
(Recreated 2026-10-25: the earlier copy was removed from the scratchpad.)"""
import subprocess
import sys
import time

RHINOCODE = "/Applications/Rhino 8.app/Contents/Resources/bin/rhinocode"

if sys.argv[1:2] == ["list"]:
    sys.exit(subprocess.run([RHINOCODE, "list"]).returncode)
if sys.argv[1:2] != ["script"] or len(sys.argv) != 3:
    sys.exit(__doc__)
p = subprocess.Popen([RHINOCODE, "script", sys.argv[2]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.5)                     # handed over; a modal box keeps it waiting, which is the caller's to watch
sys.exit(0 if p.poll() in (None, 0) else p.returncode)
