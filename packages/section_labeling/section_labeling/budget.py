"""A hard spending cap across all labeling runs.

The ledger is a small file in your home folder, outside the repository, so every checkout and worktree
on this computer shares it. It holds what has been spent: the measured cost of every finished call (the
API's own token counts × prices.yaml), plus the worst case of any call still in flight.

Each call is a transaction on the ledger, under a file lock, so runs going at the same time see each
other's spending:
  1. reserve: re-read the ledger; if what's spent plus this call's worst case could cross the cap, the
     call is never sent; otherwise the worst case is added at once.
  2. the call is made.
  3. settle: the worst case is swapped for the measured cost. If the call failed (a timeout may still
     have been billed), it stays charged at its worst case, so the cap is never underestimated.
What's spent is never taken as less than the run records in the repository add up to. The worst case
assumes every input token is billed at the highest input price (no caching) and the answer uses the
full max_tokens.
"""

import fcntl
import json
import os
from contextlib import contextmanager
from pathlib import Path


class BudgetExceeded(Exception):
    pass


class Budget:
    def __init__(self, cap_usd: float, ledger: Path, recorded_usd: float = 0.0):
        """recorded_usd: what the repository's run records add up to; the ledger is never taken as less."""
        self.cap, self.ledger, self.recorded = float(cap_usd), Path(ledger), float(recorded_usd)

    @contextmanager
    def _locked(self):
        """The ledger's contents ({spent_usd, calls}), read under an exclusive lock and written back atomically."""
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        with open(self.ledger.with_suffix(".lock"), "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            data = json.loads(self.ledger.read_text()) if self.ledger.exists() else {}
            data = {"spent_usd": max(float(data.get("spent_usd", 0.0)), self.recorded), "calls": int(data.get("calls", 0))}
            yield data
            tmp = self.ledger.with_suffix(".tmp")
            tmp.write_text(json.dumps({"spent_usd": round(data["spent_usd"], 6), "calls": data["calls"]}) + "\n")
            os.replace(tmp, self.ledger)

    @property
    def spent(self) -> float:
        with self._locked() as data:
            return data["spent_usd"]

    @property
    def remaining(self) -> float:
        return max(self.cap - self.spent, 0.0)

    def check(self, cost_usd: float) -> None:
        """Refuse a run whose estimate is more than what's left. (Reserves nothing.)"""
        if self.spent + cost_usd > self.cap:
            raise BudgetExceeded(f"needs up to ${cost_usd:.4f} but only ${self.remaining:.4f} of the "
                                 f"${self.cap:.2f} budget is left")

    def reserve(self, worst_case_usd: float) -> None:
        """Before a call: charge its worst case now, or refuse it if that could cross the cap."""
        with self._locked() as data:
            if data["spent_usd"] + worst_case_usd > self.cap:
                raise BudgetExceeded(f"a call needs up to ${worst_case_usd:.4f} but only "
                                     f"${max(self.cap - data['spent_usd'], 0):.4f} of the ${self.cap:.2f} budget is left")
            data["spent_usd"] += worst_case_usd

    def settle(self, worst_case_usd: float, cost_usd: float) -> None:
        """After a call: replace its reserved worst case with what it actually cost."""
        with self._locked() as data:
            data["spent_usd"] += cost_usd - worst_case_usd
            data["calls"] += 1


def worst_case(chars: int, settings: dict, prices: dict) -> float:
    """Upper bound for one call: ~3 characters per token (more tokens than real text has), all billed at the
    dearer of the input and cache-write prices, plus the full max_tokens of output."""
    p = prices[settings["model"]]
    return (chars / 3 * max(p["input"], p["cache_write"]) + settings["max_tokens"] * p["output"]) / 1e6
