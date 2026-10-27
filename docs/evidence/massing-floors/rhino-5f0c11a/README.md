# massing_in_rhino.py at 5f0c11a (2026-10-27)

7 of 8 (was 5 of 8 at f45c991): the shapely fix works (stages 1, 2 stories, 3 note, 4 envelope, 5 hide/show all pass).
Fails: claim 2 'the house is named the starting house'. header.main is None. The panel header only names a main building when the file has several (present.py sets main for several buildings; gordium_ui.py:573), so for one house the script's expectation is probably stale, not a product bug; left for the owner to decide. Not fixed here.
perspective.png is the capture. Dated record, never changed.
