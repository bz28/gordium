"""A state law folder's state.yaml may say which buildings its law covers (`scope`, where a state has two books for
egress: New York's Residential Code and Building Code; design_checker/code_scope.py) and what its waiting row says
(`waiting_why`); anything else there, or a scope that isn't one of the two, is a problem said in words."""

from pathlib import Path

import pytest
import yaml

from rule_format import state_law
from rule_format.rulebook import REPO, Context

NY = REPO / "regulations/jurisdictions/new_york"


@pytest.mark.parametrize("folder, scope", [("new_york_state", "residential_code"),
                                           ("new_york_state_building", "building_code")])
def test_new_yorks_two_books_each_say_which_buildings_they_cover(folder, scope):
    ctx = Context.for_jurisdiction(NY / folder, use_cache=False)
    assert state_law.state_settings_problems(NY / folder, ctx) == []
    assert yaml.safe_load((NY / folder / "state.yaml").read_text(encoding="utf-8"))["scope"] == scope


@pytest.mark.parametrize("extra, problem", [
    ({"scope": "houses"}, "scope must be one of residential_code, building_code"),
    ({"waiting_why": "  "}, "waiting_why must be words"),
    ({"colour": "red"}, "must be a mapping of name, law, results_title, scope, waiting_why and plain_words"),
    ({"plain_words": "yes"}, "plain_words must be true"),
    ({"plain_words": False, "name": " "}, "no name")])     # a bad plain_words hides no other problem
def test_a_scope_or_waiting_words_that_cant_be_used_is_a_problem(extra, problem, monkeypatch):
    real = yaml.safe_load((NY / "new_york_state/state.yaml").read_text(encoding="utf-8"))
    monkeypatch.setattr(state_law, "load", lambda p: {**real, **extra} if Path(p).name == "state.yaml" else None)
    ctx = Context.for_jurisdiction(NY / "new_york_state", use_cache=False)
    assert any(problem in p for p in state_law.state_settings_problems(NY / "new_york_state", ctx))
