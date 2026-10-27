# #26 re-lookup at 19ed22f in Rhino 8 (2026-10-27)

re_lookup_in_rhino.py stops at claim 2: 8 of 9. 'one Undo puts the sample back exactly' fails: after one Undo three objects are missing (the sample's starting house, three floors, by count). Not 41 of 41. Control: the same script on demo e760f55 gives 29 of 30 (its known claim 4 script issue), so claim 2 passed there. Owner #26: the merge of main/#23/#27 into re-lookup is the likely place to look.
