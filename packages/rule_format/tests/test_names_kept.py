"""formula.names is worked out once per formula text (formula._names). The cache must never change an answer:
the same names as a fresh walk of the formula for every formula the repository holds, a different text never gets
another text's names, an error is never kept, a caller that changes the set it got can't change what the next
caller gets, it stays bounded, and it is what makes asking again fast."""
import ast
import time

import pytest

from rule_format import formula
from rule_format.rulebook import REPO, jurisdictions, load, rulebook_paths

FORMULA_KEYS = ("applies_when", "check")


def fresh(text):
    """The walk before the cache, written out again here (nothing kept): every name, less the called ones."""
    tree = ast.parse(text, mode="eval")
    called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call)}
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} - called


def every_formula():
    """Every applies_when, check and review_when of every rulebook and answer key in the repository."""
    paths = [p for j in jurisdictions() for p in rulebook_paths(j / "5_zoning_rules")]
    paths += rulebook_paths(REPO / "test_data/answer_keys")
    out = set()
    for path in paths:
        for rule in (load(path) or {}).get("rules") or []:
            out |= {rule[k] for k in FORMULA_KEYS if isinstance(rule.get(k), str)}
            out |= {r["when"] for r in rule.get("review_when") or [] if isinstance(r.get("when"), str)}
    return sorted(out)


@pytest.fixture(autouse=True)
def empty_cache():
    formula._names.cache_clear()
    yield
    formula._names.cache_clear()


def test_there_are_formulas_to_compare():
    assert len(every_formula()) >= 10      # R-1b alone has 15; every district added is covered too


def test_every_formula_in_the_repository_has_the_same_names_cold_warm_and_fresh():
    texts = every_formula()
    cold = [formula.names(t) for t in texts]           # each worked out
    warm = [formula.names(t) for t in texts]           # each from the cache
    assert cold == warm == [fresh(t) for t in texts]
    assert formula._names.cache_info().hits == len(texts)   # the second pass really came from the cache


def test_a_different_formula_gets_its_own_names():
    """Kept by the exact text: formulas of the same length, or differing only in one name, never share."""
    assert formula.names("front_yard >= 25") == {"front_yard"}
    assert formula.names("rear_yard >= 25") == {"rear_yard"}
    assert formula.names("rear_yard >= 25.") == {"rear_yard"}
    assert formula.names("rear_yard >= lot") == {"rear_yard", "lot"}
    assert formula.names("max(a, b) >= c") == {"a", "b", "c"}       # a function name is never a measure
    assert formula.names("max >= c") == {"max", "c"}                # ... but a measure named like one is


def test_a_formula_that_does_not_parse_fails_every_time():
    for _ in range(3):
        with pytest.raises(formula.FormulaError):
            formula.names("rear_yard >=")
    assert formula._names.cache_info().currsize == 0


def test_a_caller_that_changes_its_names_never_changes_the_next_callers():
    """Callers union and subtract what they get (reading_set.rule_names: names |= ...): each gets its own set."""
    got = formula.names("rear_yard >= 25")
    assert type(got) is set
    got.add("height")
    got.discard("rear_yard")
    assert formula.names("rear_yard >= 25") == {"rear_yard"}
    assert formula.names("rear_yard >= 25") is not formula.names("rear_yard >= 25")


def test_the_cache_is_bounded():
    assert formula._names.cache_info().maxsize == formula.NAMES_KEPT
    assert len(every_formula()) < formula.NAMES_KEPT <= 100_000


def test_asking_again_is_fast():
    """A start of the Rhino command asks ~117,000 times for ~150 formulas: from the cache it must be well under
    half the time of walking each formula (~0.1x in practice; loose, for a busy machine)."""
    texts = every_formula()
    for t in texts:
        formula.parse(t)                               # the parse is kept either way: only the walk is timed

    rounds = max(20, 5000 // len(texts))               # thousands of asks, however few formulas there are

    def timed(fn):
        best = float("inf")
        for _ in range(3):
            t0 = time.perf_counter()
            for _ in range(rounds):
                for t in texts:
                    fn(t)
            best = min(best, time.perf_counter() - t0)
        return best

    formula.names(texts[0])
    walked = timed(lambda t: set(formula._names.__wrapped__(t)))
    kept = timed(formula.names)
    assert kept < 0.5 * walked, (kept, walked)
