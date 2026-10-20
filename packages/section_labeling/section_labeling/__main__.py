"""Label the pieces of a law, estimate what it costs, and report coverage.

    python -m section_labeling coverage [--check]   # write (or check) 6_coverage_report/<document>.md and the
                                                    # review list 3_section_labels/<document>.review.md; no AI
    python -m section_labeling estimate [--limit N] [--model M]
                                                    # cost before any call: exact input counts with a key
                                                    # (free token counting), a rough count without one
    python -m section_labeling label --limit N      # label the next N unlabeled pieces (or --all);
                                                    # prints the estimate, then needs --yes to spend money
    python -m section_labeling cost                 # what the recorded runs actually cost

The model and its settings come from section_labeling/settings.yaml (one place; recorded in every run).
The API key is read from ANTHROPIC_API_KEY only; a key not tied to one workspace also needs
ANTHROPIC_WORKSPACE_ID. Labeling never runs in CI; CI runs `coverage --check`.
"""

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

import yaml

from rule_format.labels import load_pieces
from rule_format.rulebook import REPO, Context, jurisdictions, load, read_jsonl

from . import coverage, labeler, term_index
from .budget import Budget, BudgetExceeded

PLACES = REPO / "regulations/jurisdictions"
LEDGER = Path.home() / ".config/gordium/section_labeling_ledger.json"   # outside the repo: shared by every checkout
MIN_CACHEABLE = 512   # tokens; shorter fixed instructions silently don't cache (Haiku/Sonnet/Opus 5.5)


def extracted_rows(j: Path, file: str) -> list[dict]:
    """A document's extracted text: a header, then one row per line ({"page", "line", "text", ...})."""
    return read_jsonl(j / "2_extracted_text" / f"{Path(file).stem}.jsonl")


def run_records(j: Path) -> list[dict]:
    """Every recorded labeling call in a jurisdiction (3_section_labels/runs/*.jsonl), oldest file first."""
    return [call for f in sorted((j / "3_section_labels/runs").glob("*.jsonl")) for call in read_jsonl(f)]


def documents(place: str | None = None):
    """(jurisdiction dir, document file name, sections file) for every document that has been cut into sections."""
    for j in jurisdictions(REPO):
        if place is not None and j.relative_to(PLACES).as_posix() != place:
            continue
        for path in sorted((j / "2_extracted_text").glob("*.sections.jsonl")):
            header, _ = load_pieces(path)
            yield j, header["file"], path


def labels_path(j: Path, file: str) -> Path:
    return j / "3_section_labels" / f"{Path(file).stem}.yaml"


def read_labels(j: Path, file: str) -> dict:
    path = labels_path(j, file)
    return (load(path) or {}).get("labels", {}) if path.exists() else {}


def _write_or_check(out: Path, text: str, check: bool) -> bool:
    """Write a generated file, or (check) say whether the saved one matches a fresh build. True when fine."""
    if check:
        same = out.exists() and out.read_text(encoding="utf-8") == text
        print(f"{'✓' if same else '✗'} {out.relative_to(REPO)}" + ("" if same else ": differs from a fresh build"))
        return same
    out.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {out.relative_to(REPO)}")
    return True


def cmd_coverage(args) -> int:
    failed = 0
    laws: dict[Path, list] = {}
    for j, file, path in documents(args.place):
        header, pieces = load_pieces(path)
        rows = extracted_rows(j, file)
        laws.setdefault(j, []).append((file, pieces, rows))
        labels = read_labels(j, file)
        bad = coverage.line_problems(rows, header, pieces)
        runs = run_records(j)
        ctx = Context.for_jurisdiction(j)
        for problem in coverage.provenance_problems(labels, runs, pieces, rows, file, ctx):
            print(f"✗ provenance: {problem}")
            failed += 1
        outputs = {j / "6_coverage_report" / f"{Path(file).stem}.md": coverage.report(rows, header, pieces, labels),
                   j / "3_section_labels" / f"{Path(file).stem}.review.md":
                       coverage.review_list(header, pieces, labels, coverage.cited_by(j, file, pieces), rows)}
        for out, text in outputs.items():
            failed += not _write_or_check(out, text, args.check)
        if bad:
            print(f"✗ {file}: {len(bad)} lines in no piece or in two (see the coverage report)")
            failed += 1
    for j, docs in laws.items():                      # the term index: every piece that uses each term or synonym
        definitions = j / "4_term_definitions/definitions.yaml"
        if definitions.exists():
            index = term_index.build(load(definitions) or {}, load(term_index.SYNONYMS_FILE) or {}, docs)
            failed += not _write_or_check(j / "4_term_definitions" / term_index.INDEX_NAME,
                                          term_index.render(index), args.check)
    return 1 if failed else 0


def _todo(j, file, path, limit, only):
    _, pieces = load_pieces(path)
    done = read_labels(j, file)
    todo = [p for i, p in pieces.items() if (i in only if only else i not in done)]
    return todo if limit is None else todo[:limit]


def _measured_output(j: Path, model: str) -> float | None:
    """Average output tokens per call in this jurisdiction's recorded runs with this model, if any."""
    calls = [c for c in run_records(j) if c["model"] == model]
    return sum(c["usage"]["output_tokens"] for c in calls) / len(calls) if calls else None


def estimate(j, file, todo, model, client=None) -> dict:
    """Projected tokens and dollars for labeling `todo`, one call each (retries not included).
    With a client, input counts are exact (count_tokens, which is free); without, ~4 characters per token."""
    rows = extracted_rows(j, file)
    system = labeler.system_prompt()
    messages = [[{"role": "user", "content": labeler.piece_message(p, rows)}] for p in todo]
    if client:
        fmt = {"effort": labeler.SETTINGS["effort"], "format": labeler.output_schema(sorted(Context.for_jurisdiction(j).topics))}
        count = lambda msgs: client.messages.count_tokens(model=model, system=system, messages=msgs,
                                                          output_config=fmt).input_tokens
        base = count([{"role": "user", "content": "."}])
        system_tokens, per_piece = base, [count(m) - base for m in messages]
    else:
        system_tokens, per_piece = len(system) // 4, [len(m[0]["content"]) // 4 for m in messages]
    cached = system_tokens >= MIN_CACHEABLE and len(todo) > 0
    measured = _measured_output(j, model)
    out_each = measured if measured is not None else labeler.SETTINGS["max_tokens"]
    usage = {"input_tokens": sum(per_piece) + (0 if cached else system_tokens * len(todo)),
             "cache_creation_input_tokens": system_tokens if cached else 0,
             "cache_read_input_tokens": system_tokens * (len(todo) - 1) if cached else 0,
             "output_tokens": round(out_each * len(todo))}
    return {"pieces": len(todo), "exact_input": bool(client), "measured_output": measured is not None,
            "system_tokens": system_tokens, "usage": usage, "cost_usd": labeler.cost(usage, model)}


def print_estimate(e: dict, model: str) -> None:
    u = e["usage"]
    print(f"  model {model}: {e['pieces']} pieces, one call each")
    print(f"  input  {u['input_tokens']:>10,} tokens ({'exact, counted by the API' if e['exact_input'] else 'ROUGH: ~4 characters per token; set ANTHROPIC_API_KEY for the exact count'})")
    print(f"  cached {u['cache_creation_input_tokens']:>10,} written once + {u['cache_read_input_tokens']:,} read "
          f"(the fixed instructions, {e['system_tokens']:,} tokens"
          + ("" if u["cache_creation_input_tokens"] else f"; below the {MIN_CACHEABLE}-token caching minimum, so not cached") + ")")
    print(f"  output {u['output_tokens']:>10,} tokens ({'measured average from recorded runs' if e['measured_output'] else 'UPPER BOUND: max_tokens per call; run --limit 10 to measure'})")
    print(f"  cost   ${e['cost_usd']:,.2f} (prices from section_labeling/prices.yaml; retries not included)")


def _client():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    import anthropic   # optional dependency: pip install -e ".[labeling]"; never needed in CI
    workspace = os.environ.get("ANTHROPIC_WORKSPACE_ID")   # needed when the key isn't tied to one workspace
    # No automatic retries: each request must pass the budget check itself (labeler.label_piece).
    return anthropic.Anthropic(api_key=key, max_retries=0,
                               default_headers={"anthropic-workspace-id": workspace} if workspace else None)


def _estimate_or_say_why(j, file, todo, model, client) -> dict | None:
    """The estimate, or None after printing why the API refused to count (a bad key, a missing workspace).
    Only the API's own errors are caught; anything else is a real problem and raises. The error class is
    taken from the SDK only if it's loaded (a real client exists only then); without it nothing is caught."""
    api_error = getattr(sys.modules.get("anthropic"), "APIError", ())
    try:
        return estimate(j, file, todo, model, client)
    except api_error as e:                       # the API's own message; it never contains the key
        print(f"  the API refused to count tokens, so nothing was sent: {getattr(e, 'message', e)}")
        return None


def cmd_estimate(args) -> int:
    model = args.model or labeler.SETTINGS["model"]
    if model not in labeler.PRICES:
        print(f"no prices for {model!r} in section_labeling/prices.yaml")
        return 1
    client = _client()
    for j, file, path in documents(args.place):
        print(f"{file}:")
        e = _estimate_or_say_why(j, file, _todo(j, file, path, args.limit, args.only), model, client)
        if e is None:
            return 1
        print_estimate(e, model)
    return 0


def cmd_label(args) -> int:
    if args.limit is None and not args.all and not args.only:
        print("say how many: --limit N, --only ID..., or --all")
        return 1
    client = _client()
    if client is None:
        print("ANTHROPIC_API_KEY is not set; nothing was sent. (`estimate` works without a key.)")
        return 1
    model = labeler.SETTINGS["model"]
    budget = Budget(labeler.SETTINGS["budget_usd"], LEDGER, recorded_spend())
    for j, file, path in documents(args.place):
        todo = _todo(j, file, path, args.limit, args.only)
        print(f"{file}:")
        e = _estimate_or_say_why(j, file, todo, model, client)
        if e is None:
            return 1
        print_estimate(e, model)
        print(f"  budget ${budget.cap:.2f}: spent ${budget.spent:.4f}, ${budget.remaining:.4f} left")
        try:
            budget.check(e["cost_usd"])
        except BudgetExceeded as stop:
            print(f"  refused: {stop} (raise budget_usd in settings.yaml to allow it)")
            return 1
        if not args.yes:
            print("  not run: add --yes to label these pieces")
            continue
        try:
            _run(client, j, file, path, todo, budget)
        except BudgetExceeded as stop:
            print(f"  stopped before a call: {stop}")
            return 1
        finally:
            print(f"  budget ${budget.cap:.2f}: spent ${budget.spent:.4f}, ${budget.remaining:.4f} left")
        cmd_coverage(argparse.Namespace(place=j.relative_to(PLACES).as_posix(), check=False))   # fresh review list
    return 0


def _run(client, j: Path, file: str, path: Path, todo: list[dict], budget: Budget | None = None) -> None:
    ctx = Context.for_jurisdiction(j)
    header, _ = load_pieces(path)
    rows = extracted_rows(j, file)
    runs = j / "3_section_labels/runs"
    runs.mkdir(parents=True, exist_ok=True)
    run_file = runs / f"{datetime.date.today():%Y-%m-%d}_{labeler.SETTINGS['model']}.jsonl"
    book_path = labels_path(j, file)
    book = load(book_path) if book_path.exists() else {"document": file, "labels": {}}
    spent, labeled, failed, skipped, errors_in_a_row = 0.0, [], [], [], 0

    def record(attempt):
        nonlocal spent
        spent += attempt["cost_usd"]
        with run_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"document": file, **attempt}, ensure_ascii=False) + "\n")

    for piece in todo:
        old = book["labels"].get(piece["id"], {})
        if old.get("status") == "approved":
            skipped.append(piece["id"])                  # an approved label is never overwritten
            continue
        try:
            entry = labeler.label_piece(client, piece, rows, file, header["sha256"], ctx, record, budget=budget)
        except BudgetExceeded:
            raise
        except Exception as e:                           # one failed request mustn't lose the rest of the run
            print(f"  {piece['id']}: request failed ({type(e).__name__})")
            failed.append(piece["id"])
            errors_in_a_row += 1
            if errors_in_a_row == 3:
                print("  stopping: 3 requests in a row failed")
                break
            continue
        errors_in_a_row = 0
        if entry is None:
            failed.append(piece["id"])
            continue
        kept = {k: old[k] for k in ("open_questions", "research", "findings", "answers", "notes") if k in old}  # survives
        book["labels"][piece["id"]] = entry | kept | {"run": run_file.relative_to(j).as_posix()}
        book_path.write_text(yaml.safe_dump(book, sort_keys=False, allow_unicode=True, width=110), encoding="utf-8")
        labeled.append(piece["id"])
    print(f"  labeled {len(labeled)}, failed {len(failed)}{': ' + ', '.join(failed) if failed else ''}, "
          f"skipped {len(skipped)} already approved; spent ${spent:.4f} (recorded in {run_file.relative_to(j).as_posix()})")


def recorded_spend() -> float:
    """The measured cost of every call in every jurisdiction's run records."""
    return sum(call["cost_usd"] for j in jurisdictions(REPO) for call in run_records(j))


def cmd_cost(args) -> int:
    for j in jurisdictions(REPO):
        for f in sorted((j / "3_section_labels/runs").glob("*.jsonl")):
            calls = read_jsonl(f)
            tokens = {k: sum(c["usage"][k] for c in calls) for k in calls[0]["usage"]} if calls else {}
            print(f"{f.relative_to(REPO)}: {len(calls)} calls, ${sum(c['cost_usd'] for c in calls):.4f}, {tokens}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m section_labeling")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("coverage", "estimate", "label", "cost"):
        p = sub.add_parser(name)
        p.add_argument("--place", help="state/place, e.g. new_york/ithaca_city (default: all)")
    sub.choices["coverage"].add_argument("--check", action="store_true", help="compare; write nothing")
    for name in ("estimate", "label"):
        sub.choices[name].add_argument("--limit", type=int, help="only the next N unlabeled pieces")
        sub.choices[name].add_argument("--only", nargs="+", default=[], help="these piece ids (relabels them)")
    sub.choices["estimate"].add_argument("--model", help="estimate another model (doesn't change settings.yaml)")
    sub.choices["label"].add_argument("--all", action="store_true", help="every unlabeled piece")
    sub.choices["label"].add_argument("--yes", action="store_true", help="spend money: actually call the API")
    args = parser.parse_args(argv)
    return {"coverage": cmd_coverage, "estimate": cmd_estimate, "label": cmd_label, "cost": cmd_cost}[args.command](args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
