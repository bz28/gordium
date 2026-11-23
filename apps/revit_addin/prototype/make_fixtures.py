"""PROTOTYPE fixtures: the checker's real answers the render-only prototype draws from.

Run from the repository root with the venv's Python:
    python apps/revit_addin/prototype/make_fixtures.py <results.jsonl> <line>
<results.jsonl> is the Revit trial's log (%LOCALAPPDATA%/Gordium/trial/results.jsonl); <line> is a Check project of
106 Ithaca Rd read in Revit 2027 (line 653 of 2026-11-22: the house, its lot facts set). Its request is sent again to
this checkout's checker (house_106.json), and once more with the lot facts the first card asks for set
(house_106_after.json: the architect's fix, for What changed). The childcare centre's answer is the committed test
answer (tests/Gordium.Revit.Reading.Tests/answers/children_odyssey_check_answer.json), not copied.
"""
import copy, json, sys
from pathlib import Path

ROOT = Path.cwd()
for p in ("packages/design_checker", "packages/model_measurement", "packages/rule_format", "packages/site_lookup",
          "packages/document_extraction"):
    sys.path.insert(0, str(ROOT / p))
from design_checker.__main__ import answer  # noqa: E402

OUT = Path(__file__).parent / "fixtures"
line = json.loads(Path(sys.argv[1]).read_text(encoding="utf8").splitlines()[int(sys.argv[2])])
request = json.loads(line["request"])
request.update({"id": 1, "cmd": "check_site", "protocol": "1.3", "today": "2026-11-22"})


def save(name, req):
    a = answer(req)
    assert a["ok"], a.get("error")
    (OUT / name).write_text(json.dumps(a, ensure_ascii=False, indent=1), encoding="utf8")
    v = a["result"]["view"]
    print(name, v["summary"], "cards:", sum(len(g.get("causes", [])) for g in v["groups"]))


save("house_106.json", request)
after = copy.deepcopy(request)
# the architect's fix: the lot facts the first card asks for, set on Project Information
after["facts"].update({"accessory_dwelling_unit": False, "stream_near_lot": False, "garage_cars": 2,
                       "owner_occupied": True, "unrelated_persons": 0, "functional_family_unit": False})
save("house_106_after.json", after)
