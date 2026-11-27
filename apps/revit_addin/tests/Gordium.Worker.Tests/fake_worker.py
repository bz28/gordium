"""A stand-in worker for the C# client's tests: it answers `hello` as the real worker does, then gives the answer
the test names, so each way an answer can go wrong (a crash, a hang, another request's id, a status Gordium doesn't
give...) is tested on purpose. The real worker is tested in RealWorkerTests.cs.

    python fake_worker.py <mode> [<file to record every byte received>]
"""

import json
import os
import sys
import time

# hello's protocol looking like 1.x to a loose reading only: a line break after it, another script's digit, a minor
# too big for a number
VERSIONS = {"hello_version_newline": "1.2\n", "hello_version_other_digit": "1.\u0662",
            "hello_version_overflow": "1.99999999999"}
# the protocol said in hello: 1.0, or GORDIUM_FAKE_PROTOCOL (the add-in's check tests send an interior, which needs 1.2)
ABOUT = {"protocol": os.environ.get("GORDIUM_FAKE_PROTOCOL", "1.0"), "site_schema": "gordium.site/1", "worker_fingerprint": "f" * 64,
         "rulebook": {"new_york/ithaca_city": "a" * 64}}
ITEM = {"id": "R-1b.height", "name": "Height", "group": "building", "status": "complies", "reason": None}
CHECK = {"view": {"items": [ITEM], "summary": "1 complies", "state": "complies"}, "report_error": None}


def ok(i, result, about=ABOUT):
    """An answer. A check's view without `groups` gets one group holding every row (the cases about the rows); a
    view whose `groups` is "-" is sent without any."""
    view = result.get("view") if isinstance(result, dict) else None
    if isinstance(view, dict) and isinstance(view.get("items"), list):
        if "groups" not in view:
            ids = [x["id"] for x in view["items"] if isinstance(x, dict) and isinstance(x.get("id"), str)]
            view = {**view, "groups": [{"key": "rows", "title": "Rows", "items": list(dict.fromkeys(ids))}]}
        elif view["groups"] == "-":
            view = {k: v for k, v in view.items() if k != "groups"}
        result = {**result, "view": view}
    return json.dumps({"id": i, "ok": True, "result": result, "about": about})


# a check as the worker gives it once the interior description says the house has no ramps (PR #112's item: one
# row per claim, design_checker/egress.py _has_none_item): zoning's row complies, egress's stair rule complies, and
# the ramp rules are set aside in one row "not applicable", with its reason. Its groups are the worker's own
# grouping of these rows (design_checker/present.grouped, PR #111), so the client is tested on the real shape: the
# row in egress's "Complies" group, folded, on a line of its own. The state is #112's present.state (a row not
# applicable counts toward nothing, so the rows that comply make the check comply).
LAW = {"group": "law", "law_key": "irc", "law": "Residential Code of New York State", "law_short": "IRC"}
NA_ITEM = {**LAW, "id": "irc.has_none.ramp", "name": "Ramps: not applicable", "status": "not_applicable", "part": None,
           "reason": "Not applicable: the description says the house has no ramps (A-2). The rules this sets aside: "
                     "Ramp slope (R318.8.1)"}
STAIR_ITEM = {**LAW, "id": "irc.stair_width#s1", "name": "Stair 1 · Stair width", "status": "complies",
              "reason": "Stair 1: Stair width: complies", "element": "Stair 1",
              "part": {"part": "stair", "id": "s1", "name": "Stair 1", "within": None}}


def egress_view(na=NA_ITEM, state="complies", line_status=None, items=None, line_of=None):
    from design_checker import present          # the worker's own grouping (the repo's, as the real worker runs it)
    items = items if items is not None else [ITEM, STAIR_ITEM, na]
    groups = present.grouped([dict(i) for i in items])
    if line_status is not None:                 # the ramps' line (or line_of's) given another status word
        for g in groups:
            for ln in g.get("lines") or []:
                if (line_of or na["id"]) in ln["items"]:
                    ln["status"] = line_status
    return {"view": {"items": items, "summary": "2 comply", "state": state, "groups": groups}, "report_error": None}


def regroup(view, groups):
    return {**view, "view": {**view["view"], "groups": groups}}


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
    # ---- not applicable (PR #112's rows), and a status word this add-in doesn't know ----
    "not_applicable": lambda i: ok(i, egress_view()),
    "not_applicable_in_review": lambda i: ok(i, egress_view(state="needs_review")),
    # a check said to comply whose only counted rows don't apply: nothing complies, so it is refused
    "complies_with_only_not_applicable": lambda i: ok(i, {"view": {"items": [dict(ITEM, group="not_covered", status="needs_review"), NA_ITEM],
                                                                   "summary": "", "state": "complies"}, "report_error": None}),
    "not_applicable_without_reason": lambda i: ok(i, egress_view(na=dict(NA_ITEM, reason=None), state="needs_review")),
    "complies_beside_not_applicable_without_reason": lambda i: ok(i, egress_view(na=dict(NA_ITEM, reason=" "))),
    # the worker's line kinder than its rows: never read kinder than its rows
    "line_kinder_than_its_rows": lambda i: ok(i, egress_view(na=dict(NA_ITEM, status="needs_review"), state="needs_review", line_status="complies")),
    "unknown_status_in_review": lambda i: ok(i, egress_view(na=dict(NA_ITEM, status="set_aside"), state="needs_review", line_status="set_aside")),
    "complies_beside_an_unknown_status": lambda i: ok(i, egress_view(na=dict(NA_ITEM, status="set_aside"))),
    "state_not_applicable": lambda i: ok(i, egress_view(state="not_applicable")),
    # ---- the groups: every row in exactly one group, and in a group with lines in exactly one line ----
    "missing_groups": lambda i: ok(i, regroup(CHECK, "-")),
    "groups_not_a_list": lambda i: ok(i, regroup(CHECK, {"rows": [ITEM["id"]]})),
    "row_in_no_group": lambda i: ok(i, regroup(egress_view(), egress_view()["view"]["groups"][1:])),
    "row_in_two_groups": lambda i: ok(i, regroup(egress_view(), egress_view()["view"]["groups"] + [{"key": "again", "title": "Again", "items": [NA_ITEM["id"]]}])),
    "group_twice": lambda i: ok(i, regroup(CHECK, [{"key": "rows", "title": "Rows", "items": [ITEM["id"]]}, {"key": "rows", "title": "Rows", "items": []}])),
    "group_names_no_row": lambda i: ok(i, regroup(CHECK, [{"key": "rows", "title": "Rows", "items": [ITEM["id"], "R-1b.ghost"]}])),
    "row_in_no_line": lambda i: ok(i, regroup(egress_view(), [egress_view()["view"]["groups"][0], {**egress_view()["view"]["groups"][1], "lines": egress_view()["view"]["groups"][1]["lines"][:1]}])),
    "line_row_not_its_groups": lambda i: ok(i, regroup(egress_view(), [egress_view()["view"]["groups"][0], {**egress_view()["view"]["groups"][1], "lines": egress_view()["view"]["groups"][1]["lines"] + [{"key": "complies#0", "title": "Height", "status": "complies", "items": [ITEM["id"]]}]}])),
    # a failing row in a group and line said to be folded (the worker never does: a failure is shown open)
    "failing_row_in_a_folded_group": lambda i: ok(i, regroup(egress_view(state="does_not_comply", items=[ITEM, dict(STAIR_ITEM, status="does_not_comply"), NA_ITEM]),
                                                             [{**g, "folded": True, "lines": [{**ln, "status": "complies", "folded": True} for ln in g.get("lines") or []] or None}
                                                              for g in egress_view(items=[ITEM, STAIR_ITEM, NA_ITEM])["view"]["groups"]])),
    # a word not known, grouped by a later worker with what complies (folded): the add-in opens it
    "unknown_status_in_a_folded_group": lambda i: ok(i, regroup(egress_view(state="needs_review", items=[ITEM, STAIR_ITEM, dict(NA_ITEM, status="set_aside")]),
                                                                egress_view()["view"]["groups"])),
    # every row complies, but the stair's line has a word not known: the line, and so its group, opened
    "unknown_line_word_in_a_folded_group": lambda i: ok(i, egress_view(state="needs_review", line_of=STAIR_ITEM["id"], line_status="set_aside")),
    "failing_line_word_in_a_folded_group": lambda i: ok(i, egress_view(state="does_not_comply", line_of=STAIR_ITEM["id"], line_status="does_not_comply")),
    # two rules on one part to review: the worker's heading counts the part's line (1), not its rows (2)
    "two_to_review_on_one_part": lambda i: ok(i, egress_view(state="needs_review", items=[ITEM, dict(STAIR_ITEM, status="needs_review"),
                                                                                   dict(STAIR_ITEM, id="irc.stair_rise#s1", name="Stair 1 · Riser height", status="needs_review")])),
    "group_count_not_a_number": lambda i: ok(i, regroup(CHECK, [{"key": "rows", "title": "Rows", "items": [ITEM["id"]], "count": "1"}])),
    "group_count_negative": lambda i: ok(i, regroup(CHECK, [{"key": "rows", "title": "Rows", "items": [ITEM["id"]], "count": -1}])),
    "lines_not_a_list": lambda i: ok(i, regroup(CHECK, [{"key": "rows", "title": "Rows", "items": [ITEM["id"]], "lines": {"a": 1}}])),
    "line_with_no_rows": lambda i: ok(i, regroup(CHECK, [{"key": "rows", "title": "Rows", "items": [ITEM["id"]], "lines": [
        {"key": "l1", "title": "Height", "status": "complies", "items": [ITEM["id"]]}, {"key": "l2", "title": "None", "status": "complies", "items": []}]}])),
    "row_in_two_lines": lambda i: ok(i, regroup(CHECK, [{"key": "rows", "title": "Rows", "items": [ITEM["id"]], "lines": [
        {"key": "l1", "title": "Height", "status": "complies", "items": [ITEM["id"]]}, {"key": "l2", "title": "Again", "status": "complies", "items": [ITEM["id"]]}]}])),
    "group_folded_not_bool":lambda i: ok(i, regroup(CHECK, [{"key": "rows", "title": "Rows", "items": [ITEM["id"]], "folded": "yes"}])),
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
    # every row a rule not in Gordium yet: nothing the check counts, so nothing it counts complies (a counted
    # not_checked row would be refused by the not_checked guard first, and this guard would go untested)
    "complies_with_nothing_complying": lambda i: ok(i, {**CHECK, "view": {**CHECK["view"], "items": [dict(ITEM, id="gap.x", group="not_covered", status="complies"), dict(ITEM, id="gap.y", group="not_covered", status="needs_review")]}}),
    "complies_beside_a_not_checked": lambda i: ok(i, {**CHECK, "view": {**CHECK["view"], "items": [ITEM, dict(ITEM, id="R-1b.bedrooms", status="not_checked")]}}),
    "complies_beside_a_release_gap": lambda i: ok(i, {**CHECK, "view": {**CHECK["view"], "items": [ITEM, dict(ITEM, id="release.overlay", group="not_checked", status="not_checked")]}}),
    "complies_use_detail_not_bool": lambda i: ok(i, {**CHECK, "view": {**CHECK["view"], "items": [dict(ITEM, use_detail="yes")]}}),
    "state_unknown": lambda i: ok(i, {**CHECK, "view": {**CHECK["view"], "state": "passes"}}),
    "report_error_not_text": lambda i: ok(i, {**CHECK, "report_error": 5}),
    "about_other_schema": lambda i: ok(i, CHECK, {**ABOUT, "site_schema": "gordium.site/2"}),
    "about_empty_fingerprint": lambda i: ok(i, CHECK, {**ABOUT, "worker_fingerprint": ""}),
    "about_rulebook_not_text": lambda i: ok(i, CHECK, {**ABOUT, "rulebook": {"new_york/ithaca_city": 5}}),
    "about_rulebook_empty": lambda i: ok(i, CHECK, {**ABOUT, "rulebook": {"new_york/ithaca_city": ""}}),
    "refused_error_not_text": lambda i: json.dumps({"id": i, "ok": False, "error": 5}),
    # "ok" twice, the last copy true: read alone (the last copy kept) it would be a good answer, so only the
    # refusal of a key given twice catches it
    "duplicate_key": lambda i: '{"ok": false, "error": "refused", ' + ok(i, CHECK)[1:],
    "duplicate_status": lambda i: ok(i, CHECK).replace('"status": "complies"', '"status": "needs_review", "status": "complies"'),
    # an escape that is half a surrogate pair: refused when read, never left to fail later at GetString
    "error_bad_escape": lambda i: '{"id": %d, "ok": false, "error": "\\ud800"}' % i,
    "status_bad_escape": lambda i: ok(i, CHECK).replace('"status": "complies"', '"status": "compl\\udc00ies"', 1),
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
    n, carry = 0, b""
    for raw in sys.stdin.buffer:
        raw, carry = carry + raw, b""                  # a request whose first byte was read on its own ("slow")
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
            if mode in VERSIONS:
                about = {**ABOUT, "protocol": VERSIONS[mode]}
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
            if mode == "slow":                         # slow to read the next request, then slow to answer it:
                carry = sys.stdin.buffer.read(1)       # timed from when it starts to arrive (its first byte), so
                time.sleep(1.5)                        # however long the client takes to begin sending, sending it
                                                       # takes at least 1.5 s of the one time limit
        elif mode == "slow":
            time.sleep(1.5)
            out.write((ok(i, CHECK) + "\n").encode("utf-8"))
        elif mode == "record":
            out.write((ok(i, CHECK) + "\n").encode("utf-8"))
        elif mode == "die":
            return 3
        elif mode == "hang":
            time.sleep(3600)
        elif mode == "beats_forever":                  # alive but getting nowhere: the same stage, forever
            while True:
                out.write((json.dumps({"id": i, "step": "Measuring the building…"}) + "\n").encode("utf-8"))
                out.flush()
                time.sleep(0.1)
        elif mode in ("beats", "beats_then_hang"):     # a long check that says it is working (only when asked)
            if request.get("progress"):
                for _ in range(1 if mode == "beats_then_hang" else 4):
                    out.write((json.dumps({"id": i, "step": "Measuring the building…"}) + "\n").encode("utf-8"))
                    out.flush()
                    time.sleep(0.5)
            if mode == "beats_then_hang":
                time.sleep(3600)
            out.write((ok(i, CHECK) + "\n").encode("utf-8"))
        else:
            line = SECOND[mode](i)
            out.write((line if isinstance(line, bytes) else line.encode("utf-8")) + b"\n")
        out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
