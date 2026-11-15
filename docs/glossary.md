# Glossary

**Purpose:** one plain-English definition for every word Gordium's documents use, so no document has to define them again.\
**For:** everyone, especially architects and shareholders new to the code, and engineers new to zoning.\
**Kept current by:** anyone who introduces a new term in a document or PR, in that same change.

Other documents link here the first time they use a term. The legal meaning of zoning words in Ithaca is the City's own wording in `regulations/jurisdictions/new_york/ithaca_city/4_term_definitions/definitions.yaml`; the entries below are everyday explanations, not the law.

## Zoning words

| Term | Meaning |
|---|---|
| <a id="zoning"></a>**Zoning** | The City's rules for what may be built where: how big, how tall, how far from the lot lines, and for what use. In Ithaca they are Chapter 325 of the City Code, plus the District Regulations Chart and the zoning map |
| <a id="district"></a>**District (zone)** | An area of the City with one set of zoning rules, named as the City writes it, e.g. **R-1b** (a low-density residential district). Gordium starts with the residential districts |
| <a id="lot"></a>**Lot (parcel)** | The piece of land a building sits on. A *tax parcel* is the County's record of a lot for property tax; its outline (the *tax map*) can be about 2 ft off, so Gordium treats it as approximate until a survey is loaded |
| <a id="survey"></a>**Survey** | A licensed surveyor's exact drawing of a lot's lines (boundary survey) or its ground levels (topographic survey) |
| <a id="yard"></a>**Yard (setback)** | The open strip a building must keep from a lot line: front, side and rear. "Setback" is the everyday word for the same distance. Example: R-1b requires a 25 ft front yard |
| <a id="corner-lot"></a>**Corner lot** | A lot on two streets. In Ithaca it has a second front yard |
| <a id="lot-coverage"></a>**Lot coverage** | The share of the lot covered by buildings, seen from above. Example: 1,600 sf of house on an 8,000 sf lot is 20% |
| <a id="grade"></a>**Grade** | The ground level around a building. Building height is measured from it |
| <a id="envelope"></a>**Envelope (buildable envelope)** | The largest space a building may fill: the lot shrunk by every required yard, up to the height limit. Gordium draws it see-through in blue |
| <a id="eave"></a>**Eave** | The edge of a roof that overhangs the wall below. Ithaca allows eaves up to 2 ft into a yard (§325-18B); see [the eaves decision](decisions/2026-10-21_eaves_need_confirmation.md) |
| <a id="variance"></a>**Variance** | Permission from the Board of Zoning Appeals (BZA) to break a zoning rule on one lot |
| <a id="bza"></a>**BZA** | The City's Board of Zoning Appeals: rules on variances and on appeals of the Zoning Administrator's interpretations |

## How Gordium talks about results

| Term | Meaning |
|---|---|
| <a id="complies"></a>**Complies (pass)** | The design meets the rule, under every reasonable reading of it |
| <a id="does-not-comply"></a>**Does not comply (fail)** | The design breaks the rule, under every reasonable reading |
| <a id="needs-review"></a>**Needs review** | Gordium can't be sure, so a person must look: missing data, an unclear rule, readings that disagree, or a measurement that failed. Gordium never says "complies" when it isn't sure |
| <a id="not-checked"></a>**Not checked** | The item exists but this release can't check it yet (e.g. overlays) |
| <a id="false-pass"></a>**False pass** | Saying "complies" when the design doesn't. The one mistake Gordium is built never to make |
| <a id="reading"></a>**Reading** | One reasonable way to understand an unclear sentence of the law. Gordium checks every reading and says "complies" only if all pass. A reading Gordium adopts is shown as "Gordium's reading · confirm with the zoning office" |
| <a id="open-question"></a>**Open question** | A point of law research couldn't settle; it goes to the architects or the City ([questions page](https://claude.ai/artifact/NDesCLC5tfFWDQJq3ah8A9)) |
| <a id="fact"></a>**Fact** | One thing Gordium knows about a project (the zone, the lot outline…), always stored as value · source · who confirmed it · date |

## How Gordium is built

| Term | Meaning |
|---|---|
| <a id="rule"></a>**Rule** | One requirement of the law as a file: the City's exact words, a yes/no formula, and worked examples |
| <a id="rulebook"></a>**Rulebook** | All the rules for one district, one file each (e.g. `R-1b.yaml`). *Frozen* rulebooks are dated versions that never change once made |
| <a id="checker"></a>**Checker** | The plain code (no AI) that reads a rulebook and a design's measurements and gives each rule its result |
| <a id="drafting"></a>**Drafting** | An AI writing a first version of rules from the law. Code then checks every word of the draft |
| <a id="answer-key"></a>**Answer key** | Rules or results worked out by hand (by the architects or by us before running Gordium), used to grade Gordium's output |
| <a id="eval"></a>**Eval** | A measured test of how good an output is, e.g. how many AI-drafted rules match the answer key |
| <a id="worker"></a>**Worker** | The Python program running in the background while Rhino is open; it measures and checks, and Rhino only draws |
| <a id="site-description"></a>**Site description** | The plain list a design tool sends the checker: the lot outline, each building as flat faces, the ground, and what was left out (`gordium.site/1`, [docs/protocol/](protocol/site_description_v1.md)). Anything in it the checker doesn't know is refused, never ignored |
| <a id="protocol"></a>**Protocol** | The agreed form of the messages between a design tool and the worker, with a version number; each side refuses a version it doesn't speak |
| <a id="artifact"></a>**Artifact (online doc)** | A web page on claude.ai, such as the System Map. Private unless shared |

## Software words

| Term | Meaning |
|---|---|
| <a id="repository"></a>**Repository (repo)** | The project's folder of files with its full history, kept on GitHub |
| <a id="commit"></a>**Commit** | One saved change to the repository, with a message saying what and why |
| <a id="branch"></a>**Branch** | A separate line of changes, worked on without touching the main version until it is merged |
| <a id="pr"></a>**PR (pull request)** | A proposed set of changes on a branch, with a description, waiting for review. Ben merges every PR |
| <a id="stack"></a>**Stack** | PRs built on top of each other: each one's starting point is the PR below it |
| <a id="ci"></a>**CI (continuous integration)** | GitHub re-running every test and check automatically on every change; a red result blocks the merge |
| <a id="test"></a>**Test** | A small program that checks one behaviour and fails loudly if it breaks |
| <a id="fingerprint"></a>**Fingerprint (SHA-256)** | A short code computed from a file's exact contents; any change to the file changes it |
| <a id="package"></a>**Package** | A folder of code that does one job (e.g. `model_measurement`) |
