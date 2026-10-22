"""Run the full Gordium CI locally under a shared slot lock: at most SLOTS full runs at once on this Mac.
Runs pytest, then every other `run: python -m ...` step in the checkout's own .github/workflows/ci.yml,
so no CI step (e.g. project_report --check) can be skipped. Exit code is non-zero if any step fails.
Usage (from a checkout's root): /Users/benzhao/Documents/Gordium/.venv/bin/python <this file> [extra pytest args]
Extra pytest args (e.g. a single test path) run pytest only, as before."""
import fcntl, os, re, subprocess, sys, time, glob
SLOTS = 2
LOCKDIR = os.path.dirname(os.path.abspath(__file__))
start = time.time(); held = None
while held is None:
    for i in range(SLOTS):
        f = open(os.path.join(LOCKDIR, f".full_suite_slot{i}.lock"), "w")
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB); held = f; break
        except BlockingIOError:
            f.close()
    if held is None:
        time.sleep(5)
waited = time.time() - start
if waited > 5:
    print(f"[full_suite] waited {waited:.0f}s for a free slot", flush=True)
# No compiled-file cache: a revert-check that restores a file of the same size within the same second would
# otherwise leave Python running the stale reverted copy (seen on r2-hand 8b3eb7e).
import shutil
for d in glob.glob("packages/**/__pycache__", recursive=True) + glob.glob("apps/**/__pycache__", recursive=True):
    shutil.rmtree(d, ignore_errors=True)
env = dict(os.environ, PYTHONPATH=os.pathsep.join(sorted(glob.glob("packages/*"))), PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1")
run = lambda cmd: subprocess.call(cmd, env=env, stdin=subprocess.DEVNULL)
code = run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *sys.argv[1:]])
if sys.argv[1:]:
    sys.exit(code)
steps = []
try:
    for line in open(".github/workflows/ci.yml"):
        m = re.search(r"run:\s*python -m (.+)$", line)
        if m and m.group(1).strip() not in steps:
            steps.append(m.group(1).strip())
except FileNotFoundError:
    print("[full_suite] no .github/workflows/ci.yml: ran pytest only", flush=True)
failed = ["pytest"] if code else []
for s in steps:
    print(f"[full_suite] python -m {s}", flush=True)
    if run([sys.executable, "-m", *s.split()]):
        failed.append(s)
print(f"[full_suite] CI steps: {len(steps) + 1} run, " + (f"FAILED: {', '.join(failed)}" if failed else "all passed"), flush=True)
sys.exit(1 if failed else 0)
