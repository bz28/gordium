"""The real checker, slowed down, for progress_cancel_in_rhino.py: before answering a check or a start it says
"Slow test: waiting…" and waits SECONDS (argv[1]), then answers exactly as `python -m design_checker serve` does
(its own steps included). Started by the plugin in place of the checker (STATE["worker_command"]); never in CI."""
import sys
import time

import design_checker.__main__ as m

DELAY = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0
real = m.answer


def answer(request, step=None):
    if request.get("cmd") in ("check", "start"):
        if step is not None:
            step("Slow test: waiting…")
        time.sleep(DELAY)
    return real(request, step)


m.answer = answer           # serve() looks it up here, so every answer goes through the wait
if __name__ == "__main__":
    sys.exit(m.main(["serve"]))
