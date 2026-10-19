# 4_term_definitions

How the City of Ithaca defines the words its rules depend on, and which uses exist. Two files:

- `definitions.yaml`: each term (height of building, grade plane, story, lot coverage, yards, lot width and depth…) with the city's own whole sentences (file, page, lines, quote, with no paraphrase) and the measurement names it defines. Gaps or ambiguities are listed under `open_questions` for the architects, never guessed. When an architect answers one, the answer moves to `answers` (question, answer, who, when) and becomes part of what they approve.
- `uses.yaml`: the primary uses in residential districts, exactly as the zoning charts name them (page 2). These are the only values the `use` measurement may take.

Where the words come from: Chapter 325 §325-3 (definitions, pp. 4–21), §325-8 (what each column of the zoning chart means, pp. 24–26), §325-18 (porches and projections in yards, p. 49), and the zoning charts p. 2 (uses).

`python -m rule_format` checks every quote against the PDF text and every measurement name. Architects confirm each entry. Later, the code that *measures* a Rhino model follows these definitions exactly.
