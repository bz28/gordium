"""The labeling script with a fake API client: no key, no network, no money. Includes the $1 budget cap.

The fake records every request, so the tests also pin what is sent (cached instructions, structured
output, effort, no temperature) and what is recorded (settings, fingerprints, tokens, cost).
"""

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from document_extraction.sections import load_rows
from rule_format.labels import load_pieces, piece_fingerprint, validate_labels
from rule_format.rulebook import Context, load
from section_labeling import __main__ as cli
from section_labeling import coverage, labeler
from section_labeling.budget import Budget, BudgetExceeded, worst_case

REPO = Path(__file__).resolve().parents[3]
ITHACA = REPO / "regulations/jurisdictions/new_york/ithaca_city"
LAW = "chapter_325_zoning_2026-10.pdf"
GOOD = {"requirements": [{"first_line": 1, "last_line": 2}],
        "label": "rule", "topic": "dimensions", "reason": "Allows extra height if yards grow.",
        "quote": "In any district, any main building may be erected to a height in excess of that"}
USAGE = {"input_tokens": 300, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 1100, "output_tokens": 80}


class FakeClient:
    """Answers each create() with the next canned answer; counts tokens as len // 4."""

    def __init__(self, *answers, stop="end_turn"):
        self.answers, self.stop, self.requests = list(answers), stop, []
        self.messages = self

    def create(self, **request):
        self.requests.append(copy.deepcopy(request))       # a snapshot: the caller's list may grow on a retry
        text = json.dumps(self.answers.pop(0))
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=self.stop,
                               usage=SimpleNamespace(**USAGE), _request_id="req_test")

    def count_tokens(self, model, system, messages, output_config):
        return SimpleNamespace(input_tokens=(len(system) + sum(len(m["content"]) for m in messages)) // 4)


@pytest.fixture(autouse=True)
def no_sdk(monkeypatch):
    """Run every test as CI does, without the Anthropic SDK installed; a test that needs it stubs it."""
    monkeypatch.setitem(sys.modules, "anthropic", None)


@pytest.fixture(autouse=True)
def private_ledger(tmp_path, monkeypatch):
    """Every test spends against its own empty ledger, never the real one in the home folder."""
    monkeypatch.setattr(cli, "LEDGER", tmp_path / "ledger.json")
    monkeypatch.setattr(cli, "recorded_spend", lambda: 0.0)


@pytest.fixture(scope="module")
def law():
    ctx = Context.for_jurisdiction(ITHACA)
    header, pieces = load_pieces(ITHACA / "2_extracted_text/chapter_325_zoning_2026-10.sections.jsonl")
    return ctx, header, pieces, load_rows(ITHACA / "2_extracted_text/chapter_325_zoning_2026-10.jsonl")


def run(law, client, pid="325-16C"):
    ctx, header, pieces, rows = law
    records = []
    entry = labeler.label_piece(client, pieces[pid], rows, LAW, header["sha256"], ctx, records.append)
    return entry, records


def test_a_good_answer_becomes_a_valid_draft_label(law):
    ctx, header, pieces, _ = law
    entry, records = run(law, FakeClient(GOOD))
    lines_6_7 = ("C. Height and open space. In any district, any main building may be erected to a height in excess of "
                 "that specified for the district, provided that: [Amended 9-6-1989 by Ord. No. 89-13]")
    assert entry["sources"] == [{"file": LAW, "page": 47, "lines": [6, 7], "quote": lines_6_7},   # L1-L2, words by code
                                {"file": LAW, "page": 47, "lines": [6, 6], "quote": GOOD["quote"]}]
    assert entry["status"] == "draft" and entry["drafted_by"] == "section_labeling/claude-haiku-5-5"
    assert validate_labels({"document": LAW, "labels": {"325-16C": entry}}, ctx, header, pieces) == []
    assert len(records) == 1


def test_what_is_sent(law):
    client = FakeClient(GOOD)
    run(law, client)
    req = client.requests[0]
    assert req["model"] == labeler.SETTINGS["model"] and req["max_tokens"] == labeler.SETTINGS["max_tokens"]
    assert req["system"][0]["cache_control"] == {"type": "ephemeral"}            # the fixed part is cached
    assert req["system"][0]["text"] == labeler.system_prompt()
    assert req["output_config"]["effort"] == labeler.SETTINGS["effort"]
    assert req["output_config"]["format"]["schema"]["required"] == ["requirements", "label", "topic", "reason", "quote"]
    assert "temperature" not in req                                              # current models reject it
    assert "C. Height and open space." in req["messages"][0]["content"]


def test_the_fixed_instructions_are_long_enough_to_cache():
    assert len(labeler.system_prompt()) // 4 >= cli.MIN_CACHEABLE


def test_what_is_recorded(law):
    _, records = run(law, FakeClient(GOOD))
    r = records[0]
    assert {"piece", "attempt", "date", "model", "effort", "max_tokens", "system_sha256", "input_sha256",
            "request_id", "stop_reason", "answer", "problem", "usage", "cost_usd"} <= r.keys()
    assert r["system_sha256"] == labeler.sha(labeler.system_prompt()) and json.loads(r["answer"]) == GOOD
    assert r["cost_usd"] == pytest.approx((300 * 0.10 + 1100 * 0.01 + 80 * 0.50) / 1e6)


def test_a_bad_quote_is_sent_back_once_then_the_corrected_answer_is_used(law):
    client = FakeClient(GOOD | {"quote": "any building may exceed the height"}, GOOD)
    entry, records = run(law, client)
    assert entry is not None and [r["problem"] for r in records] == ["the quote isn't in this piece word for word", None]
    second = client.requests[1]["messages"]
    assert second[0] == client.requests[0]["messages"][0]                       # earlier turns unchanged
    assert second[1]["role"] == "assistant" and "word for word" in second[2]["content"]


@pytest.mark.parametrize("answer", [
    GOOD | {"quote": "B. Ornamental and architectural features."},            # real words, but another piece
    GOOD | {"quote": "district"},                                              # several times in the piece
    GOOD | {"quote": "provided that"},             # once in the piece, but again lower on p.47 (not unique there)
])
def test_quotes_outside_the_piece_or_not_unique_never_become_labels(law, answer):
    entry, records = run(law, FakeClient(*[answer] * labeler.SETTINGS["max_attempts"]))
    assert entry is None and len(records) == labeler.SETTINGS["max_attempts"]


def test_a_cut_off_answer_is_not_used_or_sent_back(law):
    client = FakeClient(*[GOOD] * labeler.SETTINGS["max_attempts"], stop="max_tokens")
    entry, records = run(law, client)
    assert entry is None and records[0]["problem"] == "stopped early (max_tokens)"
    assert all(r["messages"] == client.requests[0]["messages"] for r in client.requests)   # asked afresh, no cut-off turn


def test_a_refusal_is_recorded_and_not_retried(law):
    entry, records = run(law, FakeClient(GOOD, GOOD, GOOD, stop="refusal"))
    assert entry is None and len(records) == 1 and records[0]["stop_reason"] == "refusal"


def test_estimate_without_a_key_is_rough_and_says_so(law, capsys):
    ctx, header, pieces, _ = law
    e = cli.estimate(ITHACA, LAW, list(pieces.values())[:5], "claude-haiku-5-5")
    assert not e["exact_input"] and e["usage"]["cache_read_input_tokens"] == 4 * e["system_tokens"]
    cli.print_estimate(e, "claude-haiku-5-5")
    assert "ROUGH" in capsys.readouterr().out


def test_estimate_with_a_key_counts_tokens_and_uses_measured_output(law, tmp_path, monkeypatch):
    ctx, header, pieces, _ = law
    monkeypatch.setattr(cli, "_measured_output", lambda j, model: None)        # independent of real local runs
    e = cli.estimate(ITHACA, LAW, list(pieces.values())[:5], "claude-haiku-5-5", FakeClient())
    assert e["exact_input"] and e["usage"]["output_tokens"] == 5 * labeler.SETTINGS["max_tokens"]   # nothing measured yet
    runs = tmp_path / "3_section_labels/runs"
    runs.mkdir(parents=True)
    (runs / "x.jsonl").write_text(json.dumps({"model": "claude-haiku-5-5", "usage": USAGE}) + "\n")
    monkeypatch.undo()
    assert cli._measured_output(tmp_path, "claude-haiku-5-5") == 80


def test_label_refuses_without_a_key_or_without_yes(monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert cli.main(["label", "--limit", "1"]) == 1 and "not set" in capsys.readouterr().out
    assert cli.main(["label"]) == 1 and "--limit" in capsys.readouterr().out
    client = FakeClient()
    monkeypatch.setattr(cli, "_client", lambda: client)
    assert cli.main(["label", "--limit", "2", "--place", "new_york/ithaca_city"]) == 0
    assert client.requests == [] and "add --yes" in capsys.readouterr().out    # estimate shown, nothing sent


def test_a_run_writes_labels_and_records_and_never_overwrites_an_approved_label(law, tmp_path, monkeypatch):
    approved = {"label": "flag", "status": "approved"}
    j, pieces = isolated(tmp_path, monkeypatch, law, {"325-16B": approved})
    cli._run(FakeClient(GOOD), j, LAW, Path("unused"), [pieces["325-16B"], pieces["325-16C"]])
    book = load(j / "3_section_labels/chapter_325_zoning_2026-10.yaml")
    assert book["labels"]["325-16B"] == approved and book["labels"]["325-16C"]["label"] == "rule"
    assert book["labels"]["325-16C"]["run"].startswith("3_section_labels/runs/")
    records = [json.loads(line) for f in (j / "3_section_labels/runs").glob("*.jsonl") for line in f.read_text().splitlines()]
    assert [r["piece"] for r in records] == ["325-16C"] and records[0]["document"] == LAW


def isolated(tmp_path, monkeypatch, law, labels=None):
    """A jurisdiction folder in tmp_path that uses the real Ithaca text, for runs that write files."""
    ctx, header, pieces, rows = law
    j = tmp_path / "ithaca"
    for d in ("2_extracted_text", "3_section_labels"):
        (j / d).mkdir(parents=True)
    monkeypatch.setattr(cli.Context, "for_jurisdiction", classmethod(lambda cls, _: ctx))
    monkeypatch.setattr(cli, "load_rows", lambda _: rows)
    monkeypatch.setattr(cli, "load_pieces", lambda _: (header, pieces))
    if labels:
        (j / "3_section_labels/chapter_325_zoning_2026-10.yaml").write_text(yaml.safe_dump({"document": LAW, "labels": labels}))
    return j, pieces


class FailingClient(FakeClient):
    def create(self, **request):
        self.requests.append(request)
        raise ConnectionError("network down")


def test_a_failed_request_does_not_lose_the_run_but_three_in_a_row_stop_it(law, tmp_path, monkeypatch, capsys):
    j, pieces = isolated(tmp_path, monkeypatch, law)
    client = FailingClient()
    cli._run(client, j, LAW, Path("unused"), list(pieces.values())[:5])
    out = capsys.readouterr().out
    assert len(client.requests) == 3 and "stopping: 3 requests in a row failed" in out and "failed 3" in out


def test_relabeling_keeps_a_reviewers_questions_and_counts_skipped_pieces(law, tmp_path, monkeypatch, capsys):
    doubted = {"label": "flag", "status": "draft", "open_questions": ["Really a flag?"], "notes": "see 325-16A"}
    j, pieces = isolated(tmp_path, monkeypatch, law, {"325-16C": doubted, "325-16B": {"label": "rule", "status": "approved"}})
    cli._run(FakeClient(GOOD), j, LAW, Path("unused"), [pieces["325-16B"], pieces["325-16C"]])
    label = load(j / "3_section_labels/chapter_325_zoning_2026-10.yaml")["labels"]["325-16C"]
    assert label["label"] == "rule" and label["open_questions"] == ["Really a flag?"] and label["notes"] == "see 325-16A"
    assert "labeled 1, failed 0, skipped 1 already approved" in capsys.readouterr().out


def test_spent_is_never_less_than_the_recorded_runs(tmp_path):
    assert Budget(1.00, tmp_path / "missing.json", recorded_usd=0.4).spent == 0.4
    (tmp_path / "ledger.json").write_text(json.dumps({"spent_usd": 0.7, "calls": 9}))
    assert Budget(1.00, tmp_path / "ledger.json", recorded_usd=0.4).spent == 0.7


def test_coverage_finds_lines_in_no_piece_or_two():
    rows = [{"file": "x.pdf"}] + [{"page": 1, "line": n, "text": "t"} for n in (1, 2, 3)]
    header = {"file": "x.pdf", "furniture": [[1, 1]], "problems": []}
    assert coverage.line_problems(rows, header, {"a": {"lines": [[1, 2, 3]]}}) == []
    assert coverage.line_problems(rows, header, {"a": {"lines": [[1, 2, 2]]}}) == ["p.1 line 3: in no piece"]
    assert coverage.line_problems(rows, header, {"a": {"lines": [[1, 1, 3]]}}) == ["p.1 line 1: in 2 pieces"]


def test_saved_coverage_report_is_current(capsys):
    assert cli.main(["coverage", "--check"]) == 0


def test_cited_pieces_are_found_from_the_rules_and_definitions(law):
    _, _, pieces, _ = law
    cited = coverage.cited_by(ITHACA, LAW, pieces)
    assert {"R-1b.stories", "R-1b.height"} <= set(cited["325-16C"])
    assert "R-1b.use" in cited["325-9B"] and "definitions.height_of_building" in cited["325-3B:height_of_building"]
    assert {"325-8A", "325-18A", "325-18B", "325-3B:grade_plane", "325-3B:story", "325-3B:rear_yard"} <= set(cited)


def test_review_list_shows_not_for_checking_and_cited_pieces(law):
    _, header, pieces, rows = law
    labels = {"325-1": {"label": "not_for_checking", "reason": "Just the title.", "status": "draft",
                        "sources": [{"quote": "This chapter shall be known"}]},
              "325-16C": {"label": "rule", "reason": "Height bonus.", "status": "draft", "open_questions": ["?"]},
              "325-3B:building_area": {"label": "reference", "reason": "A definition.", "status": "draft"},
              "325-3B:height_of_building": {"label": "reference", "reason": "A definition.", "status": "draft"}}
    text = coverage.review_list(header, pieces, labels, {"325-16C": ["R-1b.height"]}, rows)
    rest, cited = text.split("## Cited by")
    nfc, worded = rest.split("## Labeled reference but using requirement words")
    assert "## Open questions for the architects (1)" in worded and "| 325-16C |" in worded.split("## Open questions")[1]
    assert "| 325-3B:building_area |" in worded and "shall be located" not in nfc          # "neither ... shall be located"
    assert "325-3B:height_of_building" not in worded                         # a definition with no requirement
    more = {pid: {"label": "reference", "reason": "x", "status": "draft"}
            for pid in ("325-3B:one_family_attached_dwelling", "325-29.7A", "325-15B")}
    worded = coverage.review_list(header, pieces, labels | more, {}, rows).split("## Labeled reference but")[1]
    assert "| 325-3B:one_family_attached_dwelling |" in worded and "maximum" in worded   # "A maximum of six..."
    assert "| 325-29.7A |" in worded and "no pwsf shall" in worded                       # "No PWSF shall ..."
    assert "| 325-15B |" in worded and "shall be in conformity" in worded
    pattern = {pid: {"label": "reference", "reason": "x", "status": "draft"}
               for pid in ("325-3B:kitchenette", "325-3B:short_term_rental", "325-29.8", "325-29.7A")}
    worded = coverage.review_list(header, pieces, labels | pattern, {}, rows).split("## Labeled reference but")[1]
    for pid, words in [("325-3B:kitchenette", "less than"), ("325-3B:short_term_rental", "less than"),
                       ("325-29.8", "exceeding")]:
        assert f"| {pid} |" in worded and words in worded, pid             # patterns, not the listed instances
    assert "| 325-1 |" in nfc and "This chapter shall be known" in nfc and "325-16C" not in nfc
    assert "| 325-16C |" in cited and "draft · open questions" in cited and "R-1b.height |" in cited


# Evaluation, once real labels exist: every piece a rule or definition cites must be rule or reference,
# never dropped as "not for checking" or left for judgment.
CITED = sorted(coverage.cited_by(ITHACA, LAW, load_pieces(ITHACA / "2_extracted_text/chapter_325_zoning_2026-10.sections.jsonl")[1]))


@pytest.mark.parametrize("pid", CITED)
def test_pieces_rules_rely_on_are_rule_or_reference(pid):
    path = ITHACA / "3_section_labels/chapter_325_zoning_2026-10.yaml"
    label = (load(path)["labels"] if path.exists() else {}).get(pid)
    if label is None:
        pytest.skip("not labeled yet (needs a real labeling run)")
    assert label["label"] in ("rule", "reference"), f"{pid} labeled {label['label']}: {label['reason']}"


# The budget cap: no call is sent that could cross it, and measured spend persists across runs.
PRICE = (300 * 0.10 + 1100 * 0.01 + 80 * 0.50) / 1e6          # one fake call's measured cost (Haiku prices)


def label_with_budget(law, client, budget):
    ctx, header, pieces, rows = law
    records = []
    entry = labeler.label_piece(client, pieces["325-16C"], rows, LAW, header["sha256"], ctx, records.append, budget=budget)
    return entry, records


def test_measured_cost_is_added_and_kept_across_runs(law, tmp_path):
    ledger = tmp_path / "ledger.json"
    _, records = label_with_budget(law, FakeClient(GOOD), Budget(1.00, ledger))
    assert Budget(1.00, ledger).spent == pytest.approx(PRICE) and json.loads(ledger.read_text())["calls"] == 1
    assert records[0]["budget_usd"] == labeler.SETTINGS["budget_usd"] and records[0]["ledger_spent_usd"] == pytest.approx(PRICE)


def test_no_call_is_sent_that_could_cross_the_cap(law, tmp_path):
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({"spent_usd": 0.9999, "calls": 5000}))
    client = FakeClient(GOOD)
    with pytest.raises(BudgetExceeded, match="budget is left"):
        label_with_budget(law, client, Budget(1.00, ledger))
    assert client.requests == [] and Budget(1.00, ledger).spent == 0.9999          # nothing sent, nothing added


def test_a_retry_is_checked_too(law, tmp_path):
    _, _, pieces, rows = law
    piece = pieces["325-16C"]
    messages = [{"role": "user", "content": labeler.piece_message(piece, rows)}]
    first = worst_case(len(labeler.system_prompt()) + len(json.dumps(messages)), labeler.SETTINGS, labeler.PRICES)
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({"spent_usd": 1.00 - first - PRICE / 2, "calls": 0}))   # room for one call, not two
    client = FakeClient(GOOD | {"quote": "not in the piece at all"}, GOOD)
    with pytest.raises(BudgetExceeded):
        label_with_budget(law, client, Budget(1.00, ledger))
    assert len(client.requests) == 1                                                # the retry was never sent


def test_two_runs_at_once_share_one_ledger(tmp_path):
    ledger = tmp_path / "ledger.json"
    a, b = Budget(1.00, ledger), Budget(1.00, ledger)          # two runs, started at the same time
    a.reserve(0.6)                                             # a's call is in flight
    with pytest.raises(BudgetExceeded):
        b.reserve(0.6)                                         # b sees a's reservation
    a.settle(0.6, 0.3)
    b.reserve(0.6)
    b.settle(0.6, 0.3)
    assert Budget(1.00, ledger).spent == pytest.approx(0.6)    # neither overwrote the other


def test_a_failed_call_stays_charged_at_its_worst_case(law, tmp_path):
    ledger = tmp_path / "ledger.json"
    with pytest.raises(ConnectionError):
        label_with_budget(law, FailingClient(), Budget(1.00, ledger))
    assert Budget(1.00, ledger).spent > 0                      # a timeout may still have been billed


def test_the_sdk_does_not_retry_on_its_own_and_sends_the_workspace(monkeypatch):
    built = {}
    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=lambda **kw: built.update(kw) or "client"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("ANTHROPIC_WORKSPACE_ID", raising=False)
    assert cli._client() == "client" and built["max_retries"] == 0 and built["default_headers"] is None
    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_test")
    cli._client()
    assert built["default_headers"] == {"anthropic-workspace-id": "wrkspc_test"}


class FakeAPIError(Exception):
    message = "This API key is not scoped to a workspace"


class RefusingCounter(FakeClient):
    def count_tokens(self, **_):
        raise FakeAPIError()


def test_a_refused_token_count_stops_cleanly_before_any_call(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(APIError=FakeAPIError))
    client = RefusingCounter(GOOD)
    monkeypatch.setattr(cli, "_client", lambda: client)
    assert cli.main(["label", "--limit", "1", "--yes", "--place", "new_york/ithaca_city"]) == 1
    out = capsys.readouterr().out
    assert client.requests == [] and "nothing was sent" in out and "not scoped to a workspace" in out


def test_other_errors_while_estimating_are_not_blamed_on_the_api(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(APIError=FakeAPIError))
    monkeypatch.setattr(cli, "estimate", lambda *a: (_ for _ in ()).throw(FileNotFoundError("no extracted text")))
    monkeypatch.setattr(cli, "_client", lambda: FakeClient())
    with pytest.raises(FileNotFoundError):
        cli.main(["estimate", "--place", "new_york/ithaca_city"])


def test_worst_case_is_never_below_a_measured_call():
    measured = (300 * 0.10 + 1100 * 0.01 + 80 * 0.50) / 1e6
    assert worst_case(4 * 1400, labeler.SETTINGS, labeler.PRICES) > measured
    assert worst_case(0, labeler.SETTINGS, labeler.PRICES) >= labeler.SETTINGS["max_tokens"] * 0.50 / 1e6


def test_a_run_whose_estimate_exceeds_what_is_left_is_refused(monkeypatch, tmp_path, capsys):
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({"spent_usd": 0.99999, "calls": 1}))
    monkeypatch.setattr(cli, "LEDGER", ledger)
    client = FakeClient()
    monkeypatch.setattr(cli, "_client", lambda: client)
    assert cli.main(["label", "--only", "325-16C", "--yes", "--place", "new_york/ithaca_city"]) == 1   # independent of what is labeled
    out = capsys.readouterr().out
    assert "refused" in out and client.requests == [] and "$0.0000 left" in out


@pytest.mark.parametrize("bad, why", [
    (GOOD | {"label": "reference"}, "labeled it reference"),                  # listed a requirement, then explained it away
    (GOOD | {"requirements": []}, "listed no requirement"),                   # a rule must name the sentence that sets it
    (GOOD | {"requirements": [{"first_line": 3, "last_line": 99}]}, "cite lines between"),   # lines must exist
])
def test_answers_must_agree_with_the_requirements_they_list(law, bad, why):
    client = FakeClient(bad, GOOD)
    entry, records = run(law, client)
    assert why in records[0]["problem"] and entry["label"] == "rule" and len(records) == 2


def test_page_breaks_are_shown_and_a_citation_across_one_is_split(law):
    ctx, header, pieces, rows = law
    message = labeler.piece_message(pieces["325-29.18D"], rows)                 # L1 on p.107, L2 on p.108
    assert "L1: " in message and "--- page 108 ---\nL2: " in message
    first_line = labeler.numbered_lines(rows, pieces["325-29.18D"])[0][2]
    across = GOOD | {"requirements": [{"first_line": 1, "last_line": 2}], "quote": first_line}
    split = across | {"requirements": [{"first_line": 1, "last_line": 1}, {"first_line": 2, "last_line": 2}]}
    entry, records = run(law, FakeClient(across, split), pid="325-29.18D")
    assert "crosses a page break; cite it as one part per page: L1-L1, L2-L2" in records[0]["problem"]
    assert {s["page"] for s in entry["sources"]} == {107, 108}                  # the split answer is accepted


def test_a_repeated_cited_line_asks_for_more_lines_not_a_longer_quote(law):
    ctx, header, pieces, rows = law
    lines = labeler.numbered_lines(rows, pieces["325-3B:kitchen"])
    _, why = labeler.cited_lines({"first_line": 2, "last_line": 2}, lines, pieces["325-3B:kitchen"], LAW, ctx)
    assert "include one more line" in why and "quote more words" not in why   # repeated on the page, outside the piece


def test_a_citation_over_several_page_breaks_is_split_one_part_per_page(law):
    ctx, header, pieces, rows = law
    lines = labeler.numbered_lines(rows, pieces["325-20D"])
    pages = [p for p, _, _ in lines]
    _, why = labeler.cited_lines({"first_line": 1, "last_line": len(lines)}, lines, pieces["325-20D"], LAW, ctx)
    parts = why.split("one part per page: ")[1].split(", ")
    assert len(parts) == len(set(pages)) >= 3                                 # one part for every page, not two


def test_a_requirements_full_lines_win_over_a_quote_on_the_same_lines(law):
    one = GOOD | {"requirements": [{"first_line": 1, "last_line": 1}]}       # the quote is part of L1
    entry, _ = run(law, FakeClient(one))
    assert [s["quote"] for s in entry["sources"]] == [
        "C. Height and open space. In any district, any main building may be erected to a height in excess of that"]


def test_a_rules_sources_list_each_place_once(law):
    twice = GOOD | {"requirements": [{"first_line": 1, "last_line": 2}, {"first_line": 1, "last_line": 2}]}
    entry, _ = run(law, FakeClient(twice))
    places = [(s["page"], tuple(s["lines"])) for s in entry["sources"]]
    assert len(places) == len(set(places)) == 2                               # L1-L2 once, plus the quote's line


def test_a_copy_on_another_page_outside_the_piece_is_not_a_duplicate(law):
    ctx, header, pieces, rows = law
    lines = labeler.numbered_lines(rows, pieces["325-16F"])                   # L16 is p.48 l.12; a copy is on p.47 l.31
    source, why = labeler.cited_lines({"first_line": 16, "last_line": 16}, lines, pieces["325-16F"], LAW, ctx)
    assert why is None and (source["page"], source["lines"]) == (48, [12, 12])


def test_every_label_matches_a_recorded_answer_or_says_how_it_differs(law):
    ctx, header, pieces, rows = law
    check = lambda labels, records: coverage.provenance_problems(labels, records, pieces, rows, LAW, ctx)
    answer = GOOD                                                             # a rule citing L1-L2 of 325-16C
    records = [{"piece": "325-16C", "problem": None, "answer": json.dumps(answer)}]
    produced, _ = labeler.answer_sources(answer, pieces["325-16C"], rows, LAW, ctx)
    base = {"label": "rule", "topic": GOOD["topic"], "reason": GOOD["reason"], "sources": produced,
            "drafted_by": "section_labeling/claude-haiku-5-5"}
    assert check({"325-16C": base}, records) == []
    assert "no recorded answer has label 'flag'" in check({"325-16C": base | {"label": "flag"}}, records)[0]
    assert "with this topic and reason" in check({"325-16C": base | {"topic": "uses"}}, records)[0]
    assert "with this topic and reason" in check({"325-16C": base | {"reason": "edited by hand"}}, records)[0]
    flagged = base | {"label": "flag", "reason": "Rewritten for flag.", "revised": [{"from": "rule", "by": "x", "date": "d", "why": "w"}]}
    assert check({"325-16C": flagged}, records) == []
    extra = {"file": LAW, "page": 47, "lines": [8, 9], "quote": "(1) Each required front, side and rear yard"}
    added = base | {"sources": produced + [extra]}                            # an answer with requirements: still caught
    assert "sources differ" in check({"325-16C": added}, records)[0]
    moved = base | {"sources": [produced[0] | {"lines": [6, 6]}, *produced[1:]]}   # same words, other lines
    assert "sources differ" in check({"325-16C": moved}, records)[0]
    explained = added | {"revised": [{"field": "sources", "by": "x", "date": "d", "why": "w"}]}
    assert check({"325-16C": explained}, records) == []
    dropped = base | {"sources": [extra], "revised": explained["revised"]}    # a revision must keep what the AI produced
    assert "must keep what the recorded answer produced" in check({"325-16C": dropped}, records)[0]


def test_the_committed_labels_all_match_their_recorded_answers(law):
    ctx, header, pieces, rows = law
    labels = load(ITHACA / "3_section_labels/chapter_325_zoning_2026-10.yaml")["labels"]
    runs = [json.loads(line) for f in sorted((ITHACA / "3_section_labels/runs").glob("*.jsonl"))
            for line in f.read_text().splitlines() if line.strip()]
    assert coverage.provenance_problems(labels, runs, pieces, rows, LAW, ctx) == []
