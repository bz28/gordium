"""The registry of places: each place's settings file, regulations/jurisdictions/<state>/<place>/jurisdiction.yaml,
read and checked in one place. Code that needs to know something about a place (its name, its boundary codes, its
coordinate system, its law file, which lookup and measuring code serve it) asks here, never types it in.

    place("new_york/ithaca_city")          # by <state>/<place>, by its folder in the repo, or by any folder path
    places()                                # every place in the repo that has a settings file
    plugin_place()                          # the place the Rhino plugin checks (the only one, for now)
    only_place(who, then)                   # the one place, for a tool that reads one (else a plain error)

A place with no settings file is a plain error (UnknownPlace), never another place's settings in its stead.
Plain code, no AI.
"""

import functools
import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .rulebook import REPO, STATE_SETTINGS, building_code_rulebook

SETTINGS = "jurisdiction.yaml"
JURISDICTIONS = "regulations/jurisdictions"
# The plugin's copy of its place's settings (Rhino's Python can't read YAML): made by `python -m rule_format place
# --write`, checked current by `python -m rule_format` (CI), read by design_checker/rhino_logic.py.
PLUGIN_FILE = REPO / "packages/design_checker/design_checker/place.json"
ADAPTER_KINDS = ("lookup", "measurement")
DAYLIGHT_RULES = ("us_federal", "none")      # the daylight-saving rules rhino_logic.city_day knows
ADDRESS_LISTS = {"own_words": 1, "also_written": 0, "zip_codes": 1, "state_words": 1, "county_words": 0,
                 "nearby_places": 0, "shares_mail_with": 1}   # each list the plugin reads, and how many it needs
MATCHED_LOWERCASE = set(ADDRESS_LISTS) - {"shares_mail_with"}   # matched against a lowercased address (rhino_logic)
ONE_WORD = MATCHED_LOWERCASE - {"also_written"}           # matched word by word (also_written: as a phrase)
REQUIRED = {"name": str, "boundary": dict, "coordinates": dict, "time_zone": dict, "districts": dict, "law": dict,
            "addresses": dict, "adapters": dict}


class UnknownPlace(ValueError):
    """No settings for a place (no folder, or no jurisdiction.yaml in it), or settings that can't be used."""


@dataclass(frozen=True)
class Place:
    """One place's settings, as read from its jurisdiction.yaml (`settings`), with the values code asks for."""
    folder: Path                 # regulations/jurisdictions/<state>/<place> (absolute)
    settings: dict

    @property
    def key(self) -> str:
        """<state>/<place>, e.g. new_york/ithaca_city."""
        return f"{self.folder.parent.name}/{self.folder.name}"

    @property
    def jurisdiction(self) -> str:
        """The folder as lot facts and the checker name it: regulations/jurisdictions/<state>/<place> for a place
        in the repo, else the folder's own path (a test's place)."""
        try:
            return self.folder.relative_to(REPO).as_posix()
        except ValueError:
            return self.folder.as_posix()

    @property
    def name(self) -> str:
        return self.settings["name"]

    @property
    def swis(self) -> tuple[str, ...]:
        return tuple(str(s) for s in self.settings["boundary"].get("swis") or ())

    @property
    def neighbours(self) -> dict[str, str]:
        return {str(k): v for k, v in (self.settings["boundary"].get("neighbours") or {}).items()}

    @property
    def epsg(self) -> int:
        return int(self.settings["coordinates"]["epsg"])

    @property
    def district_column(self) -> re.Pattern:
        """A zoning-chart column that is a district, as the chart prints it."""
        return _compiled(self.settings["districts"]["chart_column"])

    @property
    def shared_columns(self) -> dict[str, list[str]]:
        """A zoning-chart column that holds several districts (as the chart prints its heading) -> those districts, as
        the city writes them (Ithaca: "Central Business" -> CBD-50 ... CBD-140, chart p.4-5)."""
        return {str(k): [str(d) for d in v] for k, v in (self.settings["districts"].get("shared_columns") or {}).items()}

    def law_file(self, role: str) -> str:
        """A document in 1_source_documents/ by what it is (zoning_code, zoning_chart)."""
        name = (self.settings.get("law") or {}).get(role)
        if not isinstance(name, str) or not name.strip():
            raise UnknownPlace(f"{self.key}: {SETTINGS} names no {role} under law")
        return name

    def adapter(self, kind: str) -> str:
        """The folder name of the place's own lookup or measuring code."""
        name = (self.settings.get("adapters") or {}).get(kind)
        if not name:
            raise UnknownPlace(f"{self.key}: {SETTINGS} names no {kind} adapter")
        return name

    @property
    def addresses(self) -> dict:
        return self.settings["addresses"]

    @property
    def time_zone(self) -> dict:
        return self.settings["time_zone"]

    @property
    def sample_site(self) -> dict | None:
        """{"folder": absolute path, "address"} of the sample lot GordiumStart offers, or None."""
        s = self.settings.get("sample_site")
        return None if not s else {"folder": REPO / s["folder"], "address": s["address"]}

    @property
    def inherits(self) -> tuple[Path, ...]:
        """The state law folders whose law applies here too (jurisdiction.yaml `inherits`, each <state>/<name>,
        a folder with a state.yaml), in the order listed: New York's Residential Code for Ithaca."""
        return tuple(self.folder.parent.parent / k for k in self.settings.get("inherits") or ())

    def inherited_rulebooks(self) -> tuple[tuple[Path, Path | None], ...]:
        """(state law folder, its rulebook or None) for each folder this place inherits, in the order listed: the
        building code rules a check of a design here runs beside the place's zoning (design_checker/egress.py).
        The one way a state's rules reach a check: through a place that inherits them."""
        return tuple((folder, building_code_rulebook(folder)) for folder in self.inherits)

    @property
    def test_sites(self) -> Path:
        """test_data/test_sites/<state>/<place>: the place's real lots and hand-worked scenarios."""
        return REPO / "test_data/test_sites" / self.key


@functools.lru_cache(maxsize=16)
def _compiled(pattern: str) -> re.Pattern:
    return re.compile(pattern)


def folder_of(where) -> Path:
    """The folder a place is named by: <state>/<place>, regulations/jurisdictions/<state>/<place> (from the repo), or
    a folder path."""
    p = Path(where)
    if p.is_absolute():
        return p
    if p.parts[:2] == tuple(JURISDICTIONS.split("/")):
        return REPO / p
    return REPO / JURISDICTIONS / p


def place(where) -> Place:
    """A place's settings. `where`: <state>/<place>, its folder in the repo (as lot facts name it), any folder, or a
    Place already read (given back as it is)."""
    if isinstance(where, Place):
        return where
    if where is None or str(where).strip() in ("", "."):
        raise UnknownPlace("no place given: say which place (regulations/jurisdictions/<state>/<place>)")
    return _read(str(folder_of(where).resolve()))


@functools.lru_cache(maxsize=32)
def _read(folder: str) -> Place:
    f = Path(folder)
    path = f / SETTINGS
    if not path.is_file():
        raise UnknownPlace(f"no settings for {_shown(f)}: {_shown(path)} is missing (every place has one: "
                           "docs/adding_a_place.md)")
    try:
        settings = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise UnknownPlace(f"{_shown(path)} can't be read: {e}") from None
    problems = settings_problems(settings)
    problems += inherit_problems(f, settings) if not problems else []
    if problems:
        raise UnknownPlace(f"{_shown(path)}: " + "; ".join(problems))
    return Place(f, settings)


def _shown(p: Path) -> str:
    try:
        return p.relative_to(REPO).as_posix()
    except ValueError:
        return p.as_posix()


def settings_problems(settings) -> list[str]:
    """What's wrong with a settings file's contents, field by field (the registry refuses a file with any)."""
    if not isinstance(settings, dict):
        return ["must be a mapping of settings"]
    out = [f"{k} must be a {t.__name__}" if k in settings else f"no {k}"
           for k, t in REQUIRED.items() if not isinstance(settings.get(k), t)]
    if out:
        return out
    if not settings["name"].strip():
        out.append("name is empty")
    if not settings["boundary"].get("swis"):
        out.append("boundary names no swis codes")
    if not isinstance(settings["coordinates"].get("epsg"), int) or isinstance(settings["coordinates"]["epsg"], bool):
        out.append("coordinates.epsg must be a whole number (the EPSG code)")
    tz = settings["time_zone"]
    if not isinstance(tz.get("standard_utc_offset_hours"), (int, float)) or isinstance(tz["standard_utc_offset_hours"], bool):
        out.append("time_zone.standard_utc_offset_hours must be a number")
    if tz.get("daylight_saving") not in DAYLIGHT_RULES:
        out.append(f"time_zone.daylight_saving must be one of {', '.join(DAYLIGHT_RULES)}")
    try:
        pattern = re.compile(str(settings["districts"].get("chart_column") or ""))
        if not settings["districts"].get("chart_column"):
            out.append("districts.chart_column is missing")
        elif pattern.fullmatch(""):
            out.append("districts.chart_column matches an empty heading (it must match only district names)")
    except re.error as e:
        out.append(f"districts.chart_column isn't a pattern ({e})")
    shared = settings["districts"].get("shared_columns")
    if shared is not None and not (isinstance(shared, dict) and shared and all(
            isinstance(k, str) and k.strip() and isinstance(v, list) and v and len(set(v)) == len(v)
            and all(isinstance(d, str) and d.strip() for d in v) for k, v in shared.items())):
        out.append("districts.shared_columns must map a chart column's heading to its list of districts")
    if not settings["law"].get("zoning_code"):
        out.append("law names no zoning_code")
    out += [f"law.{k} must name a file" for k, v in settings["law"].items() if not (isinstance(v, str) and v.strip())]
    out += [f"adapters names no {k}" for k in ADAPTER_KINDS if not settings["adapters"].get(k)]
    a = settings["addresses"]
    if not str(a.get("tail") or "").strip():
        out.append("addresses.tail is missing")
    elif not str(a["tail"]).startswith(", "):
        out.append('addresses.tail must start with ", " (it is added to the end of a typed address)')
    if not str(a.get("shares_mail_as") or "").strip():
        out.append("addresses.shares_mail_as is missing")
    for k, at_least in ADDRESS_LISTS.items():     # the plugin reads each at once (rhino_logic), so none may be missing
        words = a.get(k)
        if not isinstance(words, list) or not all(isinstance(w, str) and w.strip() for w in words):
            out.append(f"addresses.{k} must be a list of words")
        elif len(words) < at_least:
            out.append(f"addresses.{k} names none")
        elif k in MATCHED_LOWERCASE and any(w != w.lower() for w in words):
            out.append(f"addresses.{k} must be lowercase (a typed address is lowercased before it is matched)")
        elif k in ONE_WORD and any(len(w.split()) != 1 for w in words):
            out.append(f"addresses.{k} must be single words (each is matched against one word of an address)")
    site = settings.get("sample_site")
    if site is not None and not (isinstance(site, dict) and all(str(site.get(k) or "").strip()
                                                               for k in ("folder", "address"))):
        out.append("sample_site must give a folder and an address")
    return out


def inherit_problems(folder: Path, settings: dict) -> list[str]:
    """What's wrong with a place's `inherits`: a list of <state>/<name>, each a state law folder (one with a
    state.yaml) in the place's own state. Required (and not empty) once the place's state has a state law folder.
    A name that is no such folder is refused, never ignored: a place that silently inherited nothing would be
    checked against too little law."""
    names = settings.get("inherits", [])
    if not (isinstance(names, list) and all(isinstance(n, str) and n.strip() for n in names)):
        return ["inherits must be a list of state law folders (<state>/<name>)"]
    out = []
    for n in names:
        target = folder.parent.parent / n          # regulations/jurisdictions/<state>/<name>, beside the place
        if len(Path(n).parts) != 2 or Path(n).is_absolute():
            out.append(f"inherits {n!r}: name it as <state>/<name>")
        elif not (target / STATE_SETTINGS).is_file():
            out.append(f"inherits {n!r}: no state law folder there ({_shown(target / STATE_SETTINGS)} is missing)")
        elif Path(n).parts[0] != folder.parent.name:
            out.append(f"inherits {n!r}: a place inherits only its own state's law")
    if len(set(names)) != len(names):
        out.append("inherits names a folder twice")
    state_law = sorted(f"{folder.parent.name}/{s.parent.name}" for s in folder.parent.glob(f"*/{STATE_SETTINGS}"))
    if state_law and not names:
        out.append(f"inherits names no state law, but {', '.join(state_law)} is this state's: list it under inherits "
                   "(a place that silently inherited nothing would be checked against too little law)")
    return out


def stand_in(folder, name: str, inherits=()) -> Place:
    """A place with no jurisdiction.yaml (a tool's or a test's: the Children's Odyssey eval inherits Maine's state law
    alone), as the real Place, never a class of its own that copies a few. Its name, folder and the values worked out
    from them (key, jurisdiction, inherits, inherited_rulebooks, test_sites) work; the values read from
    jurisdiction.yaml's settings (boundary, coordinates, districts, time zone, law files, addresses, adapters) are
    absent and raise. A test that runs the caller through it (test_the_odyssey_answer_maker_loads_maines_law_...)
    is what catches a caller that starts reading one. `inherits`: <state>/<name> of each state law folder, as
    jurisdiction.yaml lists them."""
    return Place(Path(folder), {"name": name, "inherits": list(inherits)})


def places(repo: Path = REPO) -> list[Place]:
    """Every place under regulations/jurisdictions/ that has a settings file, in a stable order."""
    return [_read(str(p.resolve())) for p in sorted((Path(repo) / JURISDICTIONS).glob(f"*/*/{SETTINGS}"))
            for p in [p.parent]]


def only_place(who: str, then: str, repo: Path = REPO) -> Place:
    """The one place with settings, for a tool that reads one place. None, or more than one, is a plain error that
    says `then` (what to do), never the first one in its stead."""
    found = places(repo)
    if len(found) != 1:
        raise UnknownPlace(f"{who} reads one place, and {len(found)} have settings "
                           f"({', '.join(p.key for p in found) or 'none'}): {then}")
    return found[0]


def plugin_place(repo: Path = REPO) -> Place:
    """The place the Rhino plugin checks: the only place with settings, for now (a second one needs a place
    picker in the plugin first)."""
    return only_place("the plugin", "it needs a place picker first", repo)


def plugin_settings(p: Place) -> dict:
    """What the plugin's own code (rhino_logic, in Rhino's Python) needs of its place, as plain JSON data."""
    return {"jurisdiction": p.jurisdiction, "name": p.name, "time_zone": p.time_zone, "addresses": p.addresses}


def plugin_file_text(repo: Path = REPO) -> str:
    """The plugin's place.json, as `python -m rule_format place --write` writes it."""
    p = plugin_place(repo)
    body = {"_made_by": f"python -m rule_format place --write, from {_shown(p.folder / SETTINGS)}: never edit by hand",
            **plugin_settings(p)}
    return json.dumps(body, indent=1, ensure_ascii=False) + "\n"


def clear_cache() -> None:
    """Forget the settings read (a test that writes a place)."""
    _read.cache_clear()
