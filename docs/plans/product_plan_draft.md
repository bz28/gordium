# Product plan (draft)

**Purpose:** a first sketch of how Gordium reaches customers: installing, signing in, where each part runs, and what it takes to build. A draft for Ben to react to, not a decision.\
**For:** Ben, then shareholders and engineers once agreed.\
**Kept current by:** Ben and the coordinator; each choice, once made, moves into a dated decision in `docs/decisions/` and this draft links to it.

**Status: DRAFT for Ben.** Nothing here is decided. Words in links are defined in the [glossary](../glossary.md).

## The idea in one paragraph

An architect installs Gordium from Rhino's own add-on store and signs in. Checking a design happens entirely on their computer: instant, works offline, and the design never leaves the firm. What comes from us is the [rulebook](../glossary.md#rulebook) for each city, published as frozen, dated versions that update automatically.

## How it would work, piece by piece

| Piece | Proposal | Why |
|---|---|---|
| **Installing** | From Rhino's Package Manager (Yak, the same store as Food4Rhino) | Architects already install add-ons this way; one click, updates included |
| **Python** | A private Python (about 50–100 MB) bundled inside the package | Customers never install Python; it can't clash with anything else on their computer |
| **Sign-in and seats** | Sign in once per computer; a firm buys a number of seats | Standard for professional software |
| **Checking a design** | Runs locally, in the background worker that already exists | Instant, works offline, designs stay with the firm (no upload) |
| **Rulebooks** | Published from our server as frozen versions (step 7 of the pipeline), downloaded and updated automatically; every check records the version it used | Same design + same rulebook = same answer, provable later |
| **Address lookup** | Either through our server, or each copy asks the public map services directly | Through our server needs the City's and County's permission first; see [data sources and permissions](../decisions/2026-10-20_data_sources_and_permissions.md) |
| **AI drafting** | Only on our side, when a city's law changes | Principle 3: the checker never uses AI |

## Open decision: the Rhino side in Python or C#

| | Python (today) | C# |
|---|---|---|
| What changes | Nothing: today's Rhino scripts become the package | The Rhino side is rewritten as a compiled plugin |
| For | One language across the whole product; already tested in Rhino | Rhino's most mature plugin path: native panels, faster start, the usual for commercial plugins |
| Against | Rhino 8's Python plugin packaging is newer | A second language; the Rhino side's logic would exist twice unless it stays a thin shell |

Either way the measuring and checking stay in Gordium's own Python (see [how Rhino talks to Python](../decisions/2026-10-20_rhino_talks_to_python.md)).

## What it takes to build

1. **An installer:** a Yak package with the bundled Python and the Rhino commands.
2. **Step 7, frozen rulebooks:** versions that never change once published, with a version on every check.
3. **A small server** (the planned `apps/api`): serves rulebook versions, handles sign-in and seats, and optionally the address lookup.
4. **Accounts:** firms, seats, billing.

## What this draft doesn't cover yet

Pricing, support, and how a firm's own design memory (planned) is stored and kept private.
