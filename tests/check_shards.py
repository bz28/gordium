"""Proves CI's parts of the test suite add up to the whole suite: every test collected by plain `pytest` is in
exactly one `--shard K/N` part, and no part has a test the whole suite lacks. CI runs this before trusting the
parts' results (.github/workflows/ci.yml).

    python tests/check_shards.py N
"""
import subprocess
import sys
from collections import Counter


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


if __name__ == "__main__":
    main(int(sys.argv[1]))
