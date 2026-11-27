# Gordium

**Purpose:** the front door: what Gordium is, where to start reading, and how to run the tests.\
**For:** anyone new: engineers, architects, shareholders.\
**Kept current by:** whoever changes the reading path, the repository layout or how tests are run, in that same PR.

Gordium is a co-pilot inside Rhino (the 3D design program many architects use). It knows the zoning rules a building must follow and checks every design edit against them: **complies**, **does not comply**, or **needs review** when it can't be sure. Every answer points to the City's exact words. First city: the City of Ithaca, NY, residential districts first.

## Start here

Read these in order. Words you don't know are in the [glossary](docs/glossary.md).

1. **[The System Map](https://claude.ai/artifact/BMkp3eyrgemdqcwhi9oFxf)** (online, about 10 minutes): Gordium at a glance, from the City's law to a checked design, with the key decisions in one line each.
2. **[How Gordium works, step by step](https://claude.ai/artifact/5LAxAN2qpWFUMDBBDpLQrh)** (online, about 20 minutes): the same flow as plain-English pseudocode, step by step, with what is built and what isn't.
3. **[Try it](apps/rhino_plugin/QUICKSTART.md)** (about 10 minutes the first time): install Gordium in Rhino and check your first design, step by step. Or look at the [pictures](docs/demo/README.md) first.
4. **[The docs index](docs/README.md)** (5 minutes to scan): every document in this repository, what it is for and who it is for.
5. **[How we work](CLAUDE.md)** (10 minutes): the principles Gordium never breaks, the repository layout, and how changes are made and reviewed.

## How the repository is organized

Four top-level folders: `regulations/` (the City's documents and the rules made from them; data, no code), `packages/` (the code, one folder per job), `apps/` (what people use) and `test_data/` (hand-checked answers to grade Gordium against). Notes and decisions live in `docs/`. The full layout, with what each numbered step folder holds, is in [CLAUDE.md](CLAUDE.md#repository-layout).

## Running the tests

You need Python 3.12 or newer. From the repository folder:

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"   # once: set up and install
.venv/bin/pytest                                             # every test
.venv/bin/pytest -n auto                                     # the same, on every CPU (much faster)
.venv/bin/python -m rule_format                              # check every rule file
```

The full list of automatic checks that run on every change is in [.github/workflows/ci.yml](.github/workflows/ci.yml); the same checks on Windows ([.github/workflows/windows.yml](.github/workflows/windows.yml)) run nightly on main and when a PR is about to merge.
CI splits the tests into 4 parts that run at once (`pytest --shard K/4`, conftest.py) and first proves the parts add
up to the whole suite (`python tests/check_shards.py 4`).
