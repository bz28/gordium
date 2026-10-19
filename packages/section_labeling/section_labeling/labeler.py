"""Label each piece of a law with one recorded AI call, and check every answer with code.

For one piece:
  1. Send the fixed instructions (labeling_guide.md + the label kinds and topics; cached, so repeats
     are cheap) and the piece's text.
  2. The model must answer {label, topic, reason, quote} (structured output: no other shape is possible).
  3. Code finds the quote in the city's document with the same matcher the inspector uses: it must be
     exactly the city's words, inside this piece, once on its page. If not, the model is told why and
     asked again (up to max_attempts in settings.yaml); after that the piece stays unlabeled.
  4. Every attempt is recorded: settings, prompt and input fingerprints, the raw answer, tokens, cost.

The client is passed in, so tests use a fake one and never need a key or the network.
"""

import datetime
import hashlib
import json
from pathlib import Path

import yaml

from document_extraction.sections import piece_keys
from rule_format.labels import LABEL_KINDS, piece_fingerprint
from rule_format.rulebook import REPO, VOCABULARY_FILE, Context, _source_problems, locate

from .budget import worst_case

HERE = Path(__file__).parent
GUIDE_FILE = REPO / "regulations/document_extraction_guide/labeling_guide.md"
SETTINGS = yaml.safe_load((HERE / "settings.yaml").read_text())
PRICES = yaml.safe_load((HERE / "prices.yaml").read_text())


def system_prompt() -> str:
    """The fixed instructions: identical for every piece, so they're cached after the first call."""
    vocab = yaml.safe_load(VOCABULARY_FILE.read_text())
    kinds = "\n".join(f"- {k}: {' '.join(v.split())}" for k, v in vocab["label_kinds"].items())
    topics = "\n".join(f"- {k}: {' '.join(v.split())}" for k, v in vocab["topics"].items())
    return (f"{GUIDE_FILE.read_text()}\n## Label kinds (use these exact names)\n{kinds}\n\n"
            f"## Topics (use these exact names)\n{topics}\n")


def output_schema(topics: list[str]) -> dict:
    return {"type": "json_schema", "schema": {
        "type": "object", "additionalProperties": False,
        "required": ["requirements", "label", "topic", "reason", "quote"],       # requirements first: find, then label
        "properties": {"requirements": {"type": "array", "items": {         # line numbers, never copied text
                           "type": "object", "additionalProperties": False, "required": ["first_line", "last_line"],
                           "properties": {"first_line": {"type": "integer"}, "last_line": {"type": "integer"}}}},
                       "label": {"type": "string", "enum": list(LABEL_KINDS)},
                       "topic": {"type": "string", "enum": topics},
                       "reason": {"type": "string"}, "quote": {"type": "string"}}}}


def numbered_lines(rows: list[dict], piece: dict) -> list[tuple[int, int, str]]:
    """The piece's lines in order as (page, line, text); the AI cites them as L1, L2, ..."""
    text = {(r["page"], r["line"]): r["text"] for r in rows[1:]}
    return [(page, line, text[page, line]) for page, line in piece_keys(piece)]


def piece_message(piece: dict, rows: list[dict]) -> str:
    pages = sorted({p for p, _, _ in piece["lines"]})
    where = f"page {pages[0]}" if len(pages) == 1 else f"pages {pages[0]}-{pages[-1]}"
    body = "\n".join(f"L{i}: {t}" for i, (_, _, t) in enumerate(numbered_lines(rows, piece), 1))
    return (f"Piece {piece['id']}: {piece['title']} ({where}). Each line is numbered L1, L2, ...; the numbers are "
            f"not part of the city's text. Cite requirements by these line numbers.\n\n{body}")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def cost(usage: dict, model: str) -> float:
    """Dollars for one call, from its measured token counts and prices.yaml."""
    p = PRICES[model]
    return (usage["input_tokens"] * p["input"] + usage["cache_creation_input_tokens"] * p["cache_write"]
            + usage["cache_read_input_tokens"] * p["cache_read"] + usage["output_tokens"] * p["output"]) / 1e6


def cited_lines(req: dict, lines: list[tuple[int, int, str]], piece: dict, file: str,
                ctx: Context) -> tuple[dict | None, str | None]:
    """A requirement cited as L<first>..L<last>: code takes the exact words from those lines (on one page)."""
    first, last = req.get("first_line"), req.get("last_line")
    if not (isinstance(first, int) and isinstance(last, int) and 1 <= first <= last <= len(lines)):
        return None, f"cite lines between L1 and L{len(lines)}, first before last"
    span = lines[first - 1:last]
    if len({page for page, _, _ in span}) > 1:
        return None, "a requirement that crosses a page break must be cited as two parts, one per page"
    return find_quote(" ".join(t for _, _, t in span), piece, file, ctx)


def consistency_problem(answer: dict) -> str | None:
    """The label must agree with the requirements the answer itself listed."""
    if answer["requirements"] and answer["label"] in ("reference", "not_for_checking"):
        return (f"you listed {len(answer['requirements'])} requirement(s) but labeled it {answer['label']}; "
                "a piece that limits a building, lot or use is rule or flag")
    if not answer["requirements"] and answer["label"] in ("rule", "flag"):
        return f"you labeled it {answer['label']} but listed no requirement; list the sentences that set it"
    return None


def find_quote(quote: str, piece: dict, file: str, ctx: Context) -> tuple[dict | None, str | None]:
    """(source, None) if the quote is exactly the city's words inside this piece, once on its page;
    otherwise (None, why). Uses the inspector's own matcher and source check."""
    owned = set(piece_keys(piece))
    pages = ctx.pages.get(file, {})
    inside = [(page, a, b) for page in sorted({p for p, _ in owned}) for a, b in locate(quote, pages.get(page, {}))
              if (page, a) in owned and (page, b) in owned]
    if not inside:
        return None, "the quote isn't in this piece word for word"
    if len(inside) > 1:
        return None, "the quote appears more than once in this piece; quote more words so it's unique"
    page, a, b = inside[0]
    source = {"file": file, "page": page, "lines": [a, b], "quote": quote}
    if problems := _source_problems([source], ctx):
        return None, problems[0]
    return source, None


def label_piece(client, piece: dict, rows: list[dict], file: str, pdf_sha: str, ctx: Context,
                record, settings: dict = SETTINGS, budget=None) -> dict | None:
    """Label one piece. Returns the label entry, or None if no usable answer came back.
    `record(attempt_dict)` is called once per API call. With a budget, each call's worst case is reserved
    first (BudgetExceeded stops the run before the call is sent) and settled to its measured cost after;
    a call that fails stays charged at its worst case."""
    system = system_prompt()
    topics = sorted(ctx.topics)
    messages = [{"role": "user", "content": piece_message(piece, rows)}]
    lines = numbered_lines(rows, piece)
    for attempt in range(1, settings["max_attempts"] + 1):
        worst = worst_case(len(system) + len(json.dumps(messages, default=str)), settings, PRICES)
        if budget is not None:
            budget.reserve(worst)
        response = client.messages.create(                   # if this raises, the worst case stays charged
            model=settings["model"], max_tokens=settings["max_tokens"],
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
            output_config={"effort": settings["effort"], "format": output_schema(topics)})
        usage = {k: getattr(response.usage, k, 0) or 0 for k in
                 ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")}
        spent = cost(usage, settings["model"])
        if budget is not None:
            budget.settle(worst, spent)
        text = next((b.text for b in response.content if b.type == "text"), "")
        problem = answer = source = None
        if response.stop_reason != "end_turn":
            problem = f"stopped early ({response.stop_reason})"
        else:
            try:
                answer = json.loads(text)
                source, problem = find_quote(answer["quote"], piece, file, ctx)
                if not problem:
                    found = [cited_lines(r, lines, piece, file, ctx) for r in answer["requirements"]]
                    problem = next((f"requirement {r}: {why}" for r, (_, why) in zip(answer["requirements"], found)
                                    if why), None) or consistency_problem(answer)
                    if not problem and answer["label"] in ("rule", "flag"):
                        # A rule's sources are its requirement sentences: the drafting step turns each into a check.
                        source = [s for s, _ in found] + ([source] if source["lines"] not in
                                                          [s["lines"] for s, _ in found] else [])
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                problem = f"unreadable answer ({type(e).__name__})"
        record({"piece": piece["id"], "attempt": attempt, "date": datetime.datetime.now(datetime.UTC).isoformat(),
                "model": settings["model"], "effort": settings["effort"], "max_tokens": settings["max_tokens"],
                "system_sha256": sha(system), "input_sha256": sha(json.dumps(messages, sort_keys=True, default=str)),
                "request_id": getattr(response, "_request_id", None), "stop_reason": response.stop_reason,
                "answer": text, "problem": problem, "usage": usage, "cost_usd": round(spent, 6),
                "budget_usd": settings["budget_usd"], "ledger_spent_usd": round(budget.spent, 6) if budget else None})
        if source and not problem:
            return {"label": answer["label"], "topic": answer["topic"], "reason": answer["reason"].strip(),
                    "sources": source if isinstance(source, list) else [source], "piece_sha256": piece_fingerprint(piece, pdf_sha),
                    "drafted_by": f"section_labeling/{settings['model']}", "status": "draft"}
        if response.stop_reason == "refusal":
            return None            # declined: asking again won't help; recorded, and the piece stays unlabeled
        if response.stop_reason == "end_turn":
            # Tell the model why and ask again; earlier turns stay as they were (append-only).
            messages += [{"role": "assistant", "content": response.content},
                         {"role": "user", "content": f"That answer can't be used: {problem}. Answer again for the same "
                                                     "piece, citing requirements by line number and copying the quote "
                                                     "exactly from the piece's text."}]
        # A cut-off answer (max_tokens) can't be sent back; the same question is simply asked again.
    return None
