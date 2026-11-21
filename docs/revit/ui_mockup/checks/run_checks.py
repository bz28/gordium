"""Scenario checks for the UI mockup (../index.html): each scenario file is a <script> added to a copy of the mockup,
run in a headless Chromium browser (Edge or Chrome); it clicks through a flow and prints its results as name=value.
Every value must equal the expected one below. They pin the review fixes that keep stale results from ever showing as
current (never a stale green): while a check runs, after Cancel, after an edit during a check, when the state selector,
the ribbon or the Properties tab interrupts a check.

    python docs/revit/ui_mockup/checks/run_checks.py            # exit 1 on any failure; 2 when no browser is found
"""

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MOCKUP = HERE.parent / "index.html"

EXPECTED = {
    "stale_and_cancel.html": {"A_checking_stale": "true", "C_green_in_stale": "0", "B_after_cancel_stale": "true"},
    "no_results_and_edit_during_check.html": {"E_rows_while_checking": "0", "E_after_cancel_rows": "0_panel=none",
                                              "D_found_choice": "true", "D_stale_after_answer": "true"},
    "check_finishes_drawn.html": {"H_dimmed_rows": "true", "H_after_cancel_valid": "true",
                                  "F_done_drawn": "true", "G_stale_drawn": "true"},
    "interrupted_checks.html": {"I_not_current": "true", "J_cancel_keeps_results": "true"},
    "properties_tab.html": {"K_props_consistent": "true", "K_back_to_results": "true"},
}

BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "microsoft-edge", "google-chrome", "chromium", "chromium-browser",
]


def browser():
    for b in BROWSERS:
        found = shutil.which(b) or (b if Path(b).is_file() else None)
        if found:
            return found
    return None


def run(exe, scenario, work):
    page = MOCKUP.read_text(encoding="utf-8")
    script = (HERE / scenario).read_text(encoding="utf-8")
    at = page.rfind("</body>")
    target = work / scenario
    target.write_text(page[:at] + script + page[at:], encoding="utf-8")
    done = subprocess.run([exe, "--headless=new", "--disable-gpu", f"--user-data-dir={work / 'profile'}",
                           "--virtual-time-budget=9000", "--dump-dom", target.as_uri()],
                          capture_output=True, text=True, encoding="utf-8", timeout=120)
    m = re.search(r'<pre id="PIN">([^<]*)</pre>', done.stdout)
    if not m:
        return None
    return dict(part.split("=", 1) for part in m.group(1).split() if "=" in part)


def main():
    exe = browser()
    if not exe:
        print("no Edge or Chrome found: the checks did not run")
        return 2
    failed = 0
    with tempfile.TemporaryDirectory() as tmp:
        for scenario, want in EXPECTED.items():
            got = run(exe, scenario, Path(tmp))
            if got is None:
                print(f"FAIL {scenario}: no result (the scenario script did not finish)")
                failed += 1
                continue
            for key, value in want.items():
                ok = got.get(key) == value
                failed += not ok
                print(f"{'ok  ' if ok else 'FAIL'} {scenario}: {key}={got.get(key)} (want {value})")
    print(f"{failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
