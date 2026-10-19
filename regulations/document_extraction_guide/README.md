# document_extraction_guide

How we turn any regulation document into rules. Applies to every city.

- `vocabulary.yaml`: the labels we use: **label kinds** (what the system does with a piece of the law) and **topics** (how architects read the code). Draft, architects confirm.
- `labeling_guide.md`: how to label one piece of a law (rule / flag / reference / not for checking). It is the fixed instruction the labeling script sends with every piece (`packages/section_labeling`).
- `drafting_rules.md`: how to write a definition or rule from the city's words.
