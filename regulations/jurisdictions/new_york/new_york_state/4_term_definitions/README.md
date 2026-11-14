# 4_term_definitions

How the 2025 Residential Code of New York State defines the words its egress sections depend on (stair, stairway, flight, riser, nosing, winder, handrail, guard, ramp, emergency escape and rescue opening, grade plane, story above grade plane, yard, court, public way...). `definitions.yaml`: each term with the code's own whole definition (Section R202, quoted exactly with page and lines), no paraphrase.

R201.1: a word printed in italics in the code has the meaning given in Chapter 2. Every R202 definition the brought-in sections use is cut as a piece and labeled (`3_section_labels/`); this file holds the ones egress rules will measure with. Where Ithaca's zoning code defines the same word (grade plane, story, yard), the notes say so: a zoning rule uses Ithaca's definition, a building-code rule this one.

`python -m rule_format` checks every quote where the code cache has the book. No measurement names yet: egress rules come later.
