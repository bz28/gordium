"""Proves CI's parts of the test suite add up to the whole suite: every test collected by plain `pytest` is in
exactly one `--shard K/N` part, and no part has a test the whole suite lacks. CI runs this before trusting the
parts' results (.github/workflows/ci.yml).

    python tests/check_shards.py N

`record` re-measures the slow tests the parts are balanced by (tests/test_durations.json; conftest.py): it runs the
whole suite on every CPU and keeps each test of a second or more (setup + run + teardown), or reads a saved
`pytest --durations=0 --durations-min=1.0` output instead:

    python tests/check_shards.py record [pytest_output.txt]
"""
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path


def collected(*extra):
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", *extra],
                         capture_output=True, text=True, encoding="utf-8")
    ids = [line for line in out.stdout.splitlines() if "::" in line]
    if out.returncode != 0 or not ids:
        sys.exit(f"collecting {' '.join(extra) or 'the whole suite'} failed:\n{out.stdout[-3000:]}\n{out.stderr[-3000:]}")
    return ids


def main(n):
    whole = collected()
    parts = [collected("--shard", f"{k}/{n}") for k in range(1, n + 1)]
    counts = Counter(i for part in parts for i in part)
    twice = sorted(i for i, c in counts.items() if c > 1)
    missing = sorted(set(whole) - set(counts))
    extra = sorted(set(counts) - set(whole))
    print(f"whole suite: {len(whole)} tests; parts: {' + '.join(str(len(p)) for p in parts)} = {sum(map(len, parts))}")
    for name, ids in (("in two parts", twice), ("in no part", missing), ("only in a part", extra)):
        for i in ids[:20]:
            print(f"  {name}: {i}")
    if twice or missing or extra or len(whole) != len(set(whole)):
        sys.exit("the parts do not add up to the whole suite")
    print("every test is in exactly one part")


def record(saved=None):
    if saved:
        text = open(saved, encoding="utf-8").read()
    else:
        text = subprocess.run([sys.executable, "-m", "pytest", "-n", "auto", "-q", "-p", "no:cacheprovider",
                               "--durations=0", "--durations-min=1.0"], capture_output=True, text=True,
                              encoding="utf-8").stdout
    seconds = {}
    for m in re.finditer(r"^([\d.]+)s (?:setup|call|teardown) +(\S+)$", text, re.M):
        seconds[m[2]] = seconds.get(m[2], 0) + float(m[1])
    if not seconds:
        sys.exit("no durations found in the pytest output")
    out = {i: round(s, 1) for i, s in sorted(seconds.items()) if s >= 1.0}
    path = Path(__file__).resolve().parent / "test_durations.json"
    path.write_text(json.dumps(out, indent=0, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(out)} tests of a second or more, {sum(out.values()):.0f} s in all, written to {path}")


if __name__ == "__main__":
    record(*sys.argv[2:3]) if sys.argv[1] == "record" else main(int(sys.argv[1]))
