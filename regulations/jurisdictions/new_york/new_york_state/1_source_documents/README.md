# 1_source_documents

`sources.yaml` only: the book itself (the 2025 Residential Code of New York State) is copyrighted, so it is **not** in this folder. `sources.yaml` records where it came from (link), when it was downloaded, its SHA-256 fingerprint, what kind of copy it is, its terms, when it became law, and which parts of it are brought in. The book is kept in the code cache outside the repo, under its fingerprint (`kept_outside_repo: true`; [the decision](../../../../../docs/decisions/2026-11-12_building_code_text.md)). A copy of it in this folder is refused by `python -m rule_format`.
