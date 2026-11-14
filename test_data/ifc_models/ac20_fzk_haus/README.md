# AC20-FZK-Haus

**Source:** Institute for Automation and Applied Informatics (IAI) / Karlsruhe Institute of Technology (KIT)
(Institut für Automation und angewandte Informatik / Karlsruher Institut für Technologie).\
**Downloaded:** 2026-11-13 from http://www.ifcwiki.org/images/e/e3/AC20-FZK-Haus.ifc, listed on
https://www.ifcwiki.org/index.php?title=KIT_IFC_Examples ("FZK Haus", "Simple Phantasy Building", IFC 4,
ArchiCAD 20).\
**Licence:** the KIT examples page says: "These examples are made by the Institute for Applied Computer Science
(IAI) at the Karlsruhe Institute of Technology (KIT), and are for unrestricted use. If you use these examples for
publications, please provide the following source: Institute for Automation and Applied Informatics (IAI) /
Karlsruhe Institute of Technology (KIT)" (page as of 2026-11-13, last edited 2021-03-29).\
**File:** `AC20-FZK-Haus.ifc`, unchanged, 2,570,803 bytes, SHA-256
`70cc8ff245fc0894201d96496c031005a5cbd7a96b22d8a1b87c5a883fb77994`.

A made-up house (not a real building, not in Ithaca): 12 × 10 m, a ground floor (Erdgeschoss) with a bedroom
(Schlafzimmer), bath (Bad), office (Buero), living room (Wohnen), hall (Flur) and kitchen (Küche), and a gallery
(Galerie) under the roof, reached by a spiral stair (Wendeltreppe). Eleven windows (nine two-panel casements, two
round ones), five doors. No stair flights. No window is marked as an escape opening. One inner door (Innentuer-2) says
`Pset_DoorCommon.FireExit` false (read as not the exit door); the other four doors say nothing.

`AC20-FZK-Haus_interior.yaml` is what `python -m ifc_reading` makes of it. What it shows: the bedroom is read as a
sleeping room, but the office and the gallery could be slept in and say nothing more, so the rooms aren't read
(sleeping-room rules: needs review); no window is marked as an escape opening; four of the five doors don't say whether they are
the exit door, so the doors aren't read; stairs and guards aren't read.
