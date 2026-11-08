"""A stand-in worker for the C# client's tests: it answers `hello` as the real worker does, then gives the answer
the test names, so each way an answer can go wrong (a crash, a hang, another request's id, a status Gordium doesn't
give...) is tested on purpose. The real worker is tested in RealWorkerTests.cs.

    python fake_worker.py <mode> [<file to record every byte received>]
"""

import json
import sys
import time

ABOUT = {"protocol": "1.0", "site_schema": "gordium.site/1", "worker_fingerprint": "f" * 64,
         "rulebook": {"new_york/ithaca_city": "a" * 64}}
ITEM = {"id": "R-1b.height", "name": "Height", "group": "building", "status": "complies", "reason": None}
CHECK = {"view": {"items": [ITEM], "summary": "1 complies", "state": "complies"}, "report_error": None}


def ok(i, result, about=ABOUT):
    return json.dumps({"id": i, "ok": True, "result": result, "about": about})


def check(**change):
    """A check_site answer with its first item changed: a field set, or removed (None given as the string "-")."""
    item = dict(ITEM)
    for k, v in change.items():
        if v == "-":
            del item[k]
        else:
            item[k] = v
    return {**CHECK, "view": {**CHECK["view"], "items": [item]}}


# the answer to the request after hello, by mode: a function of the request's id giving the line written
SECOND = {
    "ok": lambda i: ok(i, CHECK),
    # a check that complies beside rules not in Gordium yet (not_covered) that need review: the worker's own rule
    "complies_beside_not_covered": lambda i: ok(i, {**CHECK, "view": {**CHECK["view"], "items": [ITEM, dict(ITEM, id="gap.x", group="not_covered", status="not_checked"), dict(ITEM, id="gap.y", group="not_covered", status="needs_review")]}}),
    # a check that needs review is never refused for what its rows say (the cautious direction)
    "review_with_every_row_complying": lambda i: ok(i, {**CHECK, "view": {**CHECK["view"], "state": "needs_review"}}),
    "unknown_status": lambda i: ok(i, check(status="passes")),
    "missing_status": lambda i: ok(i, check(status="-")),
    "null_status": lambda i: ok(i, check(status=None)),
    "missing_id": lambda i: ok(i, check(id="-")),
    "missing_reason": lambda i: ok(i, check(reason="-")),
    "reason_not_text": lambda i: ok(i, check(reason=3)),
    "empty_row_id": lambda i: ok(i, check(id="")),
    "missing_name": lambda i: ok(i, check(name="-")),
    "missing_group": lambda i: ok(i, check(group="-")),
    "missing_summary": lambda i: ok(i, {**CHECK, "view": {k: v for k, v in CHECK["view"].items() if k != "summary"}}),
    "complies_beside_a_fail": lambda i: ok(i, {**CHECK, "view": {**CHECK["view"], "items": [ITEM, dict(ITEM, id="R-1b.stories", status="does_not_comply")]}}),
    "complies_beside_a_review": lambda i: ok(i, {**CHECK, "view": {**CHECK["view"], "items": [ITEM, dict(ITEM, id="R-1b.stories", status="needs_review")]}}),
    "complies_with_a_use_detail": lambda i: ok(i, {**CHECK, "view": {**CHECK["view"], "items": [ITEM, dict(ITEM, id="R-1b.home_occupation", group="building", status="complies", use_detail=True)]}}),
    "complies_with_nothing_complying": lambda i: ok(i, {**CHECK, "view": {**CHECK["view"], "items": [dict(ITEM, group="not_checked", status="not_checked"), dict(ITEM, id="gap.x", group="not_covered", status="complies")]}}),
    "complies_use_detail_not_bool": lambda i: ok(i, {**CHECK, "view": {**CHECK["view"], "items": [dict(ITEM, use_detail="yes")]}}),
    "state_unknown": lambda i: ok(i, {**CHECK, "view": {**CHECK["view"], "state": "passes"}}),
    "report_error_not_text": lambda i: ok(i, {**CHECK, "report_error": 5}),
    "about_other_schema": lambda i: ok(i, CHECK, {**ABOUT, "site_schema": "gordium.site/2"}),
    "about_empty_fingerprint": lambda i: ok(i, CHECK, {**ABOUT, "worker_fingerprint": ""}),
    "about_rulebook_not_text": lambda i: ok(i, CHECK, {**ABOUT, "rulebook": {"new_york/ithaca_city": 5}}),
    "about_rulebook_empty": lambda i: ok(i, CHECK, {**ABOUT, "rulebook": {"new_york/ithaca_city": ""}}),
    "refused_error_not_text": lambda i: json.dumps({"id": i, "ok": False, "error": 5}),
    "duplicate_key": lambda i: ok(i, CHECK)[:-1] + ', "ok": false}',
    "duplicate_status": lambda i: ok(i, CHECK).replace('"status": "complies"', '"status": "needs_review", "status": "complies"'),
    "nan": lambda i: ok(i, check(limit_ft=float("nan"))),
    "empty_items": lambda i: ok(i, {**CHECK, "view": {**CHECK["view"], "items": []}}),
    "items_not_a_list": lambda i: ok(i, {**CHECK, "view": {**CHECK["view"], "items": {"a": ITEM}}}),
    "row_twice": lambda i: ok(i, {**CHECK, "view": {**CHECK["view"], "items": [ITEM, dict(ITEM, status="needs_review")]}}),
    "missing_state": lambda i: ok(i, {**CHECK, "view": {k: v for k, v in CHECK["view"].items() if k != "state"}}),
    "missing_view": lambda i: ok(i, {"report_error": None}),
    "missing_report_error": lambda i: ok(i, {"view": CHECK["view"]}),
    "no_about": lambda i: json.dumps({"id": i, "ok": True, "result": CHECK}),
    "about_2": lambda i: ok(i, CHECK, {**ABOUT, "protocol": "2.0"}),
    "no_result": lambda i: json.dumps({"id": i, "ok": True, "about": ABOUT}),
    "no_ok": lambda i: json.dumps({"id": i, "result": CHECK, "about": ABOUT}),
    "ok_text": lambda i: json.dumps({"id": i, "ok": "true", "result": CHECK, "about": ABOUT}),
    "refused": lambda i: json.dumps({"id": i, "ok": False, "error": "facts: zone is missing", "trace": "Traceback ..."}),
    "refused_no_error": lambda i: json.dumps({"id": i, "ok": False}),
    "wrong_id": lambda i: ok(i + 100, CHECK),
    "id_as_text": lambda i: ok(str(i), CHECK),
    "null_id": lambda i: json.dumps({"id": None, "ok": False, "error": "not JSON: Unexpected UTF-8 BOM"}),
    "not_json": lambda i: "Measuring the building...",
    "progress_line": lambda i: json.dumps({"id": i, "step": "Measuring the building…"}),
    "not_utf8": lambda i: b"\xff\xfe not text",
    # session answers (for facts.validate: parts value, problem, feet)
    "session_refused_and_answered": lambda i: ok(i, {"value": 3, "problem": None, "refused": {"value": "a whole number"}}),
    "session_refused_unknown_part": lambda i: ok(i, {"problem": None, "refused": {"problem2": "no"}}),
    "session_half_a_part": lambda i: ok(i, {"facts": {}}),     # box.pick: facts without saved_ui
    "session_wanted_not_given": lambda i: ok(i, {"problem": None}),
    "session_refused_words_not_text": lambda i: ok(i, {"problem": None, "refused": {"value": 3}}),
}


def main(argv):
    mode = argv[0]
    record = open(argv[1], "ab") if len(argv) > 1 else None
    out = sys.stdout.buffer
    n = 0
    for raw in sys.stdin.buffer:
        if record:
            record.write(raw)
            record.flush()
        n += 1
        request = json.loads(raw.decode("utf-8"))      # strict as the worker: a BOM makes this fail
        i = request["id"]
        if n == 1:
            about = {**ABOUT, "protocol": "2.0"} if mode == "hello_2" else ABOUT
            if mode == "hello_no_schema":
                about = {k: v for k, v in ABOUT.items() if k != "site_schema"}
            if mode == "hello_other_schema":
                about = {**ABOUT, "site_schema": "gordium.site/2"}
            if mode == "hello_bad_version":
                about = {**ABOUT, "protocol": "one"}
            if mode == "hello_crash":
                sys.stderr.write("Traceback: ImportError: no module named shapely\n")
                sys.stderr.flush()
                return 7
            if mode == "hello_hang":
                time.sleep(3600)
            out.write((ok(i, about, about) + "\n").encode("utf-8"))
            out.flush()
            if mode == "no_read":                      # stops reading its input: a large request fills the pipe
                time.sleep(3600)
            if mode == "slow":                         # slow to read the next request, then slow to answer it
                time.sleep(1.5)
        elif mode == "slow":
            time.sleep(1.5)
            out.write((ok(i, CHECK) + "\n").encode("utf-8"))
        elif mode == "record":
            out.write((ok(i, CHECK) + "\n").encode("utf-8"))
        elif mode == "die":
            return 3
        elif mode == "hang":
            time.sleep(3600)
        else:
            line = SECOND[mode](i)
            out.write((line if isinstance(line, bytes) else line.encode("utf-8")) + b"\n")
        out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
