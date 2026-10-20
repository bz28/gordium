"""Draft rules for the residential districts, estimate what it costs, and report what's drafted.

    python -m rule_drafting status                   # units drafted, rules, gaps for a person; no AI
    python -m rule_drafting estimate --limit N       # cost before any call (or --only UNIT..., --all)
    python -m rule_drafting draft --limit N          # draft the next N undrafted units; prints the
                                                     # estimate, then needs --yes to spend money
    python -m rule_drafting cost                     # what the recorded runs actually cost

A unit is one chart section (chart-p3-yard_dimensions), one piece of the law labeled rule or flag (325-16C),
or the permitted-use rules built by code from chart page 2 (chart-p2-primary_uses, free). Drafts go to
5_zoning_rules/drafted/<district>.yaml and general.yaml; the script's records (log, proposed measures,
every AI call) to 5_zoning_rules/drafted/records/. The hand-drafted 5_zoning_rules/R-1b.yaml is never
read by the drafter or overwritten: it is the answer key the drafts are graded against.

The model and budget come from rule_drafting/settings.yaml. The API key is read from ANTHROPIC_API_KEY
only (plus ANTHROPIC_WORKSPACE_ID for a key not tied to one workspace). Drafting never runs in CI.
"""

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

import yaml

from document_extraction.sections import piece_text
from rule_format import formula
from rule_format.labels import load_pieces
from rule_format.rulebook import REPO, Context, district_name, load, read_jsonl, validate, utf8_console
from section_labeling.budget import Budget, BudgetExceeded
from section_labeling.labeler import numbered_lines

from . import chart_values, drafter
from .templates import CHART_FILE
from .uses import SECTION as USES_SECTION, use_rule

PLACE = REPO / "regulations/jurisdictions/new_york/ithaca_city"
LEDGER = Path.home() / ".config/gordium/rule_drafting_ledger.json"   # outside the repo: shared by every checkout
LAW_FILE = "chapter_325_zoning_2026-10.pdf"
USES_UNIT = "chart-p2-primary_uses"
ACCESSORY_UNIT = "chart-p2-accessory_uses"
CODE_SECTIONS = {(2, USES_SECTION): USES_UNIT, (2, "Accessory Uses"): ACCESSORY_UNIT}   # built by code, not the AI
DRAFTED_LABELS = ("rule", "flag")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", re.sub(r"\[fn[^\]]*\]", "", text).lower()).strip("_")


class Inputs:
    """Everything drafting reads, for one jurisdiction."""

    def __init__(self, j: Path = PLACE):
        self.j, self.drafted, self.records = j, j / "5_zoning_rules/drafted", j / "5_zoning_rules/drafted/records"
        self.ctx = Context.for_jurisdiction(j)
        stem = Path(CHART_FILE).stem
        _, self.tables, cells = chart_values.load_cells(j / f"2_extracted_text/{stem}.cells.jsonl")
        self.cells_list = cells
        self.cells = {(c["page"], c["section"], c["row"].strip(), c["column"]): c for c in cells if not c["heading"]}
        self.columns = chart_values.districts(self.tables)
        chart_rows = read_jsonl(j / f"2_extracted_text/{stem}.jsonl")
        self.notes = {t["page"]: chart_values.notes_under_table(chart_rows[1:], t["page"], t["bottom"]) for t in self.tables}
        law_header, pieces = load_pieces(j / f"2_extracted_text/{Path(LAW_FILE).stem}.sections.jsonl")
        self.law = {"file": law_header["file"], "pieces": pieces,
                    "rows": read_jsonl(j / f"2_extracted_text/{Path(LAW_FILE).stem}.jsonl")}
        labels_file = j / f"3_section_labels/{Path(LAW_FILE).stem}.yaml"
        self.labels = (load(labels_file) or {}).get("labels", {}) if labels_file.exists() else {}
        self.uses = load(j / "4_term_definitions/uses.yaml")
        self.definitions = load(j / "4_term_definitions/definitions.yaml")
        # Every section of every chart page the reader read; the use lists are built by code, not the AI.
        pages = sorted({t["page"] for t in self.tables})
        self.chart_sections = [s for s in chart_values.sections(cells, pages) if s not in CODE_SECTIONS]

    def rows_of(self, page, section):
        return chart_values.section_rows(self.cells_list, page, section)

    def system(self) -> str:
        return drafter.system_prompt(self.ctx, self.uses, [district_name(c) for c in self.columns],
                                     drafter.chart_table(self.chart_sections, self.rows_of), self.notes)

    def units(self) -> list[dict]:
        out = [{"id": unit_id, "code": True} for unit_id in CODE_SECTIONS.values()]
        for page, section in self.chart_sections:
            head = chart_values.heading(self.cells_list, page, section)
            rows = self.rows_of(page, section)
            text = "\n".join([f"Section heading: {head['row'].strip() if head else section}"] + [
                f"- row {label!r} (chart page {page}, line{'s' if len(next(iter(cells.values()))['row_lines']) > 1 else ''} "
                f"{', '.join(map(str, next(iter(cells.values()))['row_lines']))}): "
                + " | ".join(f"{col}: {c['value']}" for col, c in cells.items()) for label, cells in rows.items()])
            out.append({"id": f"chart-p{page}-{slug(section)}", "page": page, "section": section, "prefix": "",
                        "intro": (f"Zoning chart page {page}, section {section!r}. Draft templates for the requirements "
                                  "these rows set for the residential districts. Every number from a row is a slot."),
                        "text": text})
        for pid, label in self.labels.items():
            if label.get("label") in DRAFTED_LABELS and pid in self.law["pieces"]:
                piece = self.law["pieces"][pid]
                out.append({"id": pid, "piece": pid, "prefix": f"{slug(pid)}_",
                            "intro": (f"Piece {pid} of the zoning law (document \"law\", piece id {pid}): {piece['title']}. "
                                      f"It was labeled {label['label']}: {label['reason']} Draft the rules it sets for "
                                      "the residential districts."),
                            "text": piece_text(self.law["rows"], piece),
                            # the input is the whole piece, every line numbered; the label's sources are only hints
                            # (older labels may cite just a heading or lead-in), but each must end with a rule or a person
                            "lines": numbered_lines(self.law["rows"], piece),
                            "requirements": [s for s in label.get("sources", []) if s.get("file") == self.law["file"]]})
        return out


def read_log(i: Inputs) -> dict:
    path = i.records / "drafting_log.yaml"
    return (load(path) or {}) if path.exists() else {"units": {}, "complete": False}


def rulebook_path(i: Inputs, district: str) -> Path:
    return i.drafted / f"{district}.yaml"


def owned_rules_approved(i: Inputs, log: dict, unit_id: str) -> bool:
    owned = set(log["units"].get(unit_id, {}).get("rules", []))
    for path in i.drafted.glob("*.yaml"):
        for r in (load(path) or {}).get("rules", []):
            if r.get("id") in owned and r.get("status") == "approved":
                return True
    return False


def save_result(i: Inputs, log: dict, unit_id: str, result: dict) -> None:
    """Replace this unit's earlier drafts with the new ones, and record what happened."""
    old = set(log["units"].get(unit_id, {}).get("rules", []))
    books = {p.stem: load(p) for p in i.drafted.glob("*.yaml")}
    for district, book in books.items():
        book["rules"] = [r for r in book.get("rules", []) if r["id"] not in old]
    new_ids = []
    for district, rules in result["rules"].items():
        book = books.setdefault(district, {"district": district, "rules": []})
        taken = {r["id"] for r in book["rules"]}
        for rule in rules:
            if rule["id"] in taken:
                result.setdefault("unresolved", []).append(
                    {"rule": rule["id"], "why": "the id is already drafted by another unit; not saved"})
                continue
            book["rules"].append(rule)
            taken.add(rule["id"])
            new_ids.append(rule["id"])
    i.drafted.mkdir(parents=True, exist_ok=True)
    for district, book in books.items():
        path = rulebook_path(i, district)
        if book["rules"]:
            path.write_text(yaml.safe_dump(book, sort_keys=False, allow_unicode=True, width=110), encoding="utf-8")
        elif path.exists():
            path.unlink()
    entry = {"rules": new_ids, "unresolved": result.get("unresolved", []), "problems": result.get("problems", [])}
    if result.get("reason"):
        entry["reason"] = result["reason"]
    if result.get("failed"):
        entry["failed"] = result["failed"]
    log["units"][unit_id] = entry
    # The engineers' to-do list is rebuilt from the saved rules every time: a measure is needed by exactly the
    # rules whose formulas name it (by name, not by substring), and one no rule uses any more is dropped.
    proposed_path = i.records / "proposed_measures.yaml"
    known = ((load(proposed_path) or {}) if proposed_path.exists() else {}) | {
        name: {"unit": m["unit"], "meaning": m["meaning"]} for name, m in result.get("proposed", {}).items()}
    proposed = {}
    for book in books.values():
        for rule in book["rules"]:
            for name in sorted((_formula_names(rule) & set(known)) - i.ctx.measures):   # added since: not a to-do
                entry_m = proposed.setdefault(name, {"unit": known[name]["unit"], "meaning": known[name]["meaning"],
                                                     "needed_by": []})
                entry_m["needed_by"] = sorted(set(entry_m["needed_by"]) | {rule["id"]})
    i.records.mkdir(parents=True, exist_ok=True)
    if proposed:
        proposed_path.write_text(yaml.safe_dump(proposed, sort_keys=True, allow_unicode=True, width=110), encoding="utf-8")
    elif proposed_path.exists():
        proposed_path.unlink()
    (i.records / "drafting_log.yaml").write_text(yaml.safe_dump(log, sort_keys=False, allow_unicode=True, width=110), encoding="utf-8")


def _formula_names(rule: dict) -> set[str]:
    """The measure names a rule's formulas use."""
    texts = [rule.get("applies_when"), rule.get("check")] + [r.get("when") for r in rule.get("review_when") or []]
    return {n for t in texts if isinstance(t, str) and t.strip() for n in formula.names(t)}


def run_records(i: Inputs) -> list[dict]:
    """Every recorded drafting call (drafted/records/runs/*.jsonl), oldest file first."""
    return [call for f in sorted((i.records / "runs").glob("*.jsonl")) for call in read_jsonl(f)]


def recorded_spend(i: Inputs) -> float:
    return sum(call.get("cost_usd", 0) for call in run_records(i))


def _measured_output(i: Inputs, model: str) -> float | None:
    calls = [c for c in run_records(i) if c["model"] == model and c.get("stop_reason") == "end_turn"]
    return sum(c["usage"]["output_tokens"] for c in calls) / len(calls) if calls else None


def select(i: Inputs, log: dict, args) -> list[dict]:
    units = [u for u in i.units() if args.kind == "all" or (args.kind == "chart") == u["id"].startswith("chart-")]
    if args.only:
        missing = sorted(set(args.only) - {u["id"] for u in units})
        if missing:
            raise SystemExit(f"no such unit: {', '.join(missing)} (see `python -m rule_drafting status`)")
        return [u for u in units if u["id"] in args.only]
    todo = [u for u in units if u["id"] not in log["units"]]
    return todo if args.limit is None else todo[:args.limit]


def estimate(i: Inputs, todo: list[dict], model: str, client=None) -> dict:
    """Upper-bound cost before any call: exact input counts with a key (free token counting), else ~4
    characters per token; output at the measured average of recorded calls, else max_tokens."""
    ai = [u for u in todo if not u.get("code")]
    system = i.system()
    messages = [drafter.unit_message(u, drafter.gather_context(u, i.law, {"notes": i.notes}, i.definitions)) for u in ai]
    if client is not None and ai:           # exact, counted the way a call is sent (instructions and answer schema too)
        fmt = {"effort": drafter.SETTINGS["effort"], "format": drafter.output_schema(sorted(i.ctx.topics))}
        count = lambda text: client.messages.count_tokens(model=model, system=system, output_config=fmt,
                                                          messages=[{"role": "user", "content": text}]).input_tokens
        system_tokens = count(".")
        tokens = sum(count(m) - system_tokens for m in messages)
    else:
        system_tokens, tokens = len(system) // 4, sum(len(m) // 4 for m in messages)
    out_each = _measured_output(i, model) or drafter.SETTINGS["max_tokens"]
    usage = {"input_tokens": tokens, "cache_creation_input_tokens": system_tokens if ai else 0,
             "cache_read_input_tokens": system_tokens * max(len(ai) - 1, 0), "output_tokens": int(out_each * len(ai))}
    return {"units": len(todo), "ai_calls": len(ai), "exact_input": client is not None, "usage": usage,
            "measured_output": _measured_output(i, model) is not None, "cost_usd": drafter.cost(usage, model)}


def print_estimate(e: dict, model: str) -> None:
    u = e["usage"]
    print(f"  model {model}: {e['units']} units, {e['ai_calls']} AI calls (retries not included)")
    print(f"  input   {u['input_tokens']:,} tokens ({'exact, counted by the API' if e['exact_input'] else 'ROUGH: ~4 characters per token'})")
    print(f"  cached  {u['cache_creation_input_tokens']:,} written once + {u['cache_read_input_tokens']:,} read (the fixed instructions)")
    print(f"  output  {u['output_tokens']:,} tokens ({'measured average' if e['measured_output'] else 'UPPER BOUND: max_tokens per call'})")
    print(f"  cost    ${e['cost_usd']:.2f} (prices from section_labeling/prices.yaml; confirm before a large run)")


def _client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    import anthropic
    headers = {"anthropic-workspace-id": os.environ["ANTHROPIC_WORKSPACE_ID"]} if os.environ.get("ANTHROPIC_WORKSPACE_ID") else None
    return anthropic.Anthropic(max_retries=0, default_headers=headers)


def cmd_status(args) -> int:
    i = Inputs()
    log = read_log(i)
    units = i.units()
    done = [u for u in units if u["id"] in log["units"]]
    rules = sum(len(e["rules"]) for e in log["units"].values())
    gaps = sum(len(e.get("unresolved", [])) for e in log["units"].values())
    failed = [k for k, e in log["units"].items() if e.get("failed")]
    print(f"{len(done)} of {len(units)} units drafted; {rules} rules; {gaps} district rules for a person; "
          f"{len(failed)} units with no usable answer{': ' + ', '.join(failed) if failed else ''}")
    return 0


def cmd_estimate(args) -> int:
    i = Inputs()
    model = args.model or drafter.SETTINGS["model"]
    todo = select(i, read_log(i), args)
    print_estimate(estimate(i, todo, model, _client()), model)
    return 0


def cmd_draft(args) -> int:
    if args.limit is None and not args.all and not args.only:
        print("say how many: --limit N, --only UNIT..., or --all")
        return 1
    i = Inputs()
    log = read_log(i)
    todo = select(i, log, args)
    client = None
    if any(not u.get("code") for u in todo):
        client = _client()
        if client is None:
            print("ANTHROPIC_API_KEY is not set; nothing was sent. (`estimate` works without a key.)")
            return 1
    model = drafter.SETTINGS["model"]
    budget = Budget(drafter.SETTINGS["budget_usd"], LEDGER, recorded_spend(i))
    e = estimate(i, todo, model, client)
    print_estimate(e, model)
    print(f"  budget ${budget.cap:.2f}: spent ${budget.spent:.4f}, ${budget.remaining:.4f} left")
    try:
        budget.check(e["cost_usd"])
    except BudgetExceeded as stop:
        print(f"  refused: {stop} (raise budget_usd in settings.yaml to allow it)")
        return 1
    if not args.yes:
        print("  not run: add --yes to draft these units")
        return 0
    run_file = i.records / "runs" / f"{datetime.date.today().isoformat()}_{model}.jsonl"
    run_file.parent.mkdir(parents=True, exist_ok=True)

    def record(attempt):
        with run_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(attempt, default=str) + "\n")

    system = i.system() if client else ""
    saved = False
    try:
        for u in todo:
            if owned_rules_approved(i, log, u["id"]):
                print(f"  {u['id']}: skipped, an architect approved its rules")
                continue
            if u["id"] == USES_UNIT:
                result = draft_uses(i)
            elif u["id"] == ACCESSORY_UNIT:
                result = draft_accessory()
            else:
                context = drafter.gather_context(u, i.law, {"notes": i.notes}, i.definitions)
                result = drafter.draft_unit(client, u, context, system, i.law, i.ctx, i.columns, i.cells, i.notes,
                                            record, budget=budget)
            save_result(i, log, u["id"], result)
            saved = True
            print(f"  {u['id']}: {sum(len(r) for r in result['rules'].values())} rules, "
                  f"{len(result.get('unresolved', []))} for a person"
                  + (f", none: {result['reason']}" if result.get("reason") else "")
                  + (f", FAILED: {result['failed']}" if result.get("failed") else ""))
    except BudgetExceeded as stop:
        print(f"  stopped before a call: {stop}")
        return 1
    finally:
        print(f"  budget ${budget.cap:.2f}: spent ${budget.spent:.4f}, ${budget.remaining:.4f} left")
        if saved:                               # however the run ended: what's saved is cited in the review list
            refresh_review_list(i)
    log["complete"] = all(u["id"] in log["units"] for u in i.units())
    (i.records / "drafting_log.yaml").write_text(yaml.safe_dump(log, sort_keys=False, allow_unicode=True, width=110), encoding="utf-8")
    return 0


def refresh_review_list(i: Inputs) -> None:
    """The labels' review list lists the pieces drafted rules cite, so a drafting run rewrites it (the same
    command the labeling run ends with); otherwise CI's `section_labeling coverage --check` fails after it."""
    from section_labeling.__main__ import PLACES, cmd_coverage
    if i.j.is_relative_to(PLACES):
        cmd_coverage(argparse.Namespace(place=i.j.relative_to(PLACES).as_posix(), check=False))


def draft_accessory() -> dict:
    """Chart page 2's accessory uses (ADU, private garage, home occupation...): not drafted yet, on purpose.
    The `use` measure is a lot's primary use; which accessory uses a design has needs a measure of its own,
    which an engineer adds first. Recorded with the reason, so a complete run can't hide it."""
    return {"rules": {}, "unresolved": [], "problems": [], "proposed": {},
            "reason": ("Not drafted: accessory uses need a measure of which accessory uses a design has "
                       "(the use measure is the primary use). An engineer adds it, then this unit is drafted.")}


def draft_uses(i: Inputs) -> dict:
    """The permitted-use rule for every district, built by code from chart page 2 (no AI, no cost)."""
    rows = i.rows_of(2, USES_SECTION)
    result = {"rules": {}, "unresolved": [], "problems": [], "proposed": {}}
    for column in i.columns:
        heading = {n for t in i.tables if t["page"] == 2 for c in t["columns"] if c["name"] == column
                   for h in c["headers"] for n in chart_values.footnotes(h)}
        rule, problems, notes_for_a_person = use_rule(column, rows, i.uses, i.notes.get(2, {}),
                                                      "rule_drafting/chart_code", heading)
        if rule is not None and (bad := validate({"district": rule["id"].split(".")[0], "rules": [rule]}, i.ctx)):
            problems, rule = problems + bad, None
        if rule is None:
            result["unresolved"].append({"rule": f"{district_name(column)}.use", "why": "; ".join(problems)})
        else:
            result["rules"][rule["id"].split(".")[0]] = [rule]
            result["problems"] += problems
            result["unresolved"] += notes_for_a_person
    return result


def cmd_cost(args) -> int:
    i = Inputs()
    calls = run_records(i)
    print(f"{len(calls)} recorded calls, ${sum(c['cost_usd'] for c in calls):.4f}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m rule_drafting")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "estimate", "draft", "cost"):
        sub.add_parser(name)
    for name in ("estimate", "draft"):
        p = sub.choices[name]
        p.add_argument("--limit", type=int, help="only the next N undrafted units")
        p.add_argument("--only", nargs="+", default=[], help="these unit ids (drafts them again)")
        p.add_argument("--all", action="store_true", help="every undrafted unit")
        p.add_argument("--kind", choices=("all", "chart", "law"), default="all", help="chart sections, law pieces, or both")
    sub.choices["estimate"].add_argument("--model", help="estimate another model (doesn't change settings.yaml)")
    sub.choices["draft"].add_argument("--yes", action="store_true", help="spend money: actually call the API")
    args = parser.parse_args(argv)
    return {"status": cmd_status, "estimate": cmd_estimate, "draft": cmd_draft, "cost": cmd_cost}[args.command](args)


if __name__ == "__main__":
    utf8_console()
    sys.exit(main(sys.argv[1:]))
