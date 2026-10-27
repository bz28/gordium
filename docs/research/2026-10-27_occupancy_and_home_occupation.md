# Research: who may live in a dwelling, and home occupations (City of Ithaca, Chapter 325)

**Purpose:** the research behind the occupancy and home-occupation rules added to every residential hand rulebook on 2026-10-27 (`<district>.occupancy_one_family`, `.occupancy_two_family`, `.home_occupation_size`, `.home_occupation`): what the law says, what was searched, how each question was classified.\
**For:** anyone checking why Gordium reads these rules the way it does; architects confirming a reading.\
**Kept current by:** nobody: a dated record. New research gets its own dated report.

Chapter 325 quotes are from Gordium's stored copy
(`regulations/jurisdictions/new_york/ithaca_city/2_extracted_text/chapter_325_zoning_2026-10.jsonl`); page numbers
are that PDF's pages. Chart quotes are from `zoning_charts_2026-04.pdf`.

**Class** (as in `2026-10-20_architect_questions.md`): **A** = answered by the code's own text; **B** = Gordium's
reading, well sourced, shown to the architect to confirm; **C** = genuinely unclear, an open question.

**What was searched, in Ben's order.**
1. The code text: every §325-3B definition the term index reaches from "family", "unrelated", "occupant",
   "owner-occupied", "functional family unit", "home occupation", "dwelling, one-family / two-family / multiple",
   "cooperative household", "rooming house"; §325-8B(6); §325-9B(1)(i), E(1), F(1)(b); §325-20 (parking for a home
   occupation); the zoning chart p.2 (use rows and notes 1 and 4).
2. City interpretations and BZA records: a web search on 2026-10-27 ("City of Ithaca zoning occupancy unrelated R-3
   one-family minor dependent children interpretation") found no City interpretation or BZA decision on these
   questions; the results were the code itself, a third-party copy of an older §325-8 chart
   (https://www.fhia.org/wp-content/uploads/Minutes/Ithaca_zoning_regulations_section_325-8.pdf, which reads "plus
   not more than two unrelated occupants" for a one-family dwelling: the older text, superseded) and Town of Ithaca
   cases (another code).
3. and 4. NYS / IBC commentary and other cities: not needed; every question below is settled by the code's own
   text or kept as a reading.

## 1. Who is an "unrelated individual"? — A

§325-3B FAMILY (p.9): "One or more persons occupying a dwelling unit, all of whom are related by blood, marriage or
adoption." DWELLING, ONE-FAMILY (p.7): "an individual or family and not more than one unrelated individual or a
functional family unit". So the unrelated people are those not related by blood, marriage or adoption to the
household's family; a household with no family starts from one individual, and everyone else in it is unrelated.
Gordium asks, per lot, the most such people in any one dwelling unit (`unrelated_persons`).

## 2. Minor dependent children

### 2.1 In R-1 and R-2 — A

§325-8B(6) (p.26-27) and chart p.2 note 1: "In R-1 and R-2 Districts, minor dependent children in the care of a
parent or relative shall be excluded in determining the number of unrelated occupants in a dwelling unit."
`unrelated_persons` leaves them out.

### 2.2 Outside R-1 and R-2 (R-3, RU) — B

The exclusion is written for "R-1 and R-2 Districts" only, and the one-family definition has none of its own, while
the multiple-dwelling and cooperative-household definitions write theirs out ("exclusive of minor dependent
children in the care of a parent or relative"). Gordium's reading: in R-3 and RU they are counted
(`unrelated_persons_with_children`). It is the cautious reading: counting them can make a dwelling need review or
not comply, never pass when it shouldn't. To confirm with the architects.

## 3. R-1: two unrelated people if owner-occupied — A

p.7: "In the R-1 Zones, occupancy by an individual or a family and not more than two unrelated individuals is
permitted if the dwelling is owner-occupied." OWNER (p.16-17): an owner of record "who maintains his/her principal
residence in property for more than six months of each calendar year". Gordium asks `owner_occupied` (yes / no);
blank, a household of two unrelated people needs review.

**With an accessory dwelling unit — B.** If the owner lives only in an ADU on the lot, is the one-family dwelling
"owner-occupied"? The sentence says "if the dwelling is owner-occupied"; a one-family dwelling is "A dwelling unit"
(p.7) and an ADU is "a smaller, secondary dwelling unit" of its own (p.4); OWNER defines who the owner is
("principal residence in property"), not which unit; §325-28 (ADUs, p.71-72) sets no owner-occupancy rule. Gordium's
reading: the owner must live in the dwelling unit with the unrelated people. The question is asked that way ("this
dwelling unit, the one with the unrelated people, not only an accessory dwelling unit"), so a yes is right under every
reading and an owner living only in the ADU answers no (the limit of one: at worst a false fail, never a false pass).
To confirm with the architects.

## 4. RU's limit — B

The definition raises the one-unrelated-person limit only "In the R-1 Zones" (owner-occupied) and "In the R-2 and
R-3 Zones". The code names R-U as a district of its own beside R-3 (e.g. §325-9B(1)(e) "R-2, CR-2 and R-U
Districts"; §325-20 "an R-3 or R-U district"). Gordium's reading: RU keeps the first sentence's limit, one
unrelated person (children counted, §2.2). The cautious reading; to confirm with the architects.

## 5. A functional family unit — A (the City's finding)

FUNCTIONAL FAMILY UNIT (p.10-11) lists criteria that "must be present" (sharing the whole unit; stability, shown by
children, shared expenses, the same address for voting, licences and taxes, shared furniture, a year together...)
and presumptions against (four or more college students; four or more unrelated adults with no minor dependent
children). Weighing them is the City's job, case by case. Gordium asks `functional_family_unit` only as the
architect's statement that the household will be shown to be one: over the limit, "yes" sends the row to review,
"no" makes it not comply, blank needs review.

## 6. Each unit of a two-family dwelling

### 6.1 In R-2 — A

p.9: "In R-2 and CR-2 Zones, each unit of a two-family dwelling may be occupied by an individual or family and not
more than two unrelated individuals." Children left out (§2.1).

### 6.2 In R-3 and RU — B

The two-family definition sets per-unit limits only for R-1/CR-1 and R-2/CR-2. Elsewhere the limit is where the
building stops being a two-family dwelling: a unit occupied by "a group of four or more unrelated persons, exclusive
of minor dependent children in the care of a parent or relative" (DWELLING, MULTIPLE (2), p.7), or a building
"occupied by one or two families and more than two roomers or boarders" ((3), p.7; §6.4). Gordium reads "a group of
four or more unrelated persons" as four people none related to another, so a household's family member and three
people unrelated to it can make one (a reading, to confirm with the architects). With §6.4 open, a unit with more
than one unrelated person needs review ("check it as a multiple dwelling": its own lot size and rules). Never a fail:
a multiple dwelling is permitted in these districts under its own rules.

### 6.3 In R-1 — not checked

Two-family dwellings aren't permitted in R-1a or R-1b (chart p.2), so the use rule already fails them; the R-1
per-unit limits of p.9 (one unrelated person, the single-occupant exception, the owner-occupied floor-area split)
are left for a grandfathered two-family dwelling, which Gordium doesn't check.

### 6.4 Are unrelated housemates "roomers or boarders"? — C (open question for the architects)

DWELLING, MULTIPLE (3) (p.7): "A building containing living, sanitary and sleeping facilities occupied by one or two
families and more than two roomers or boarders, exclusive of minor dependent children in the care of a parent or
relative, residing with either one of such families." "Roomer" and "boarder" aren't defined. BOARDINGHOUSE (p.5)
speaks of meals provided for compensation to long-term guests, and FUNCTIONAL FAMILY UNIT (p.10) sets "separate
roomers" against a household sharing the whole unit, which points to lodgers who pay; but nothing says an unrelated
housemate isn't one. If they count, an R-2 two-family dwelling with two unrelated individuals in each unit (four in
the building, which the two-family definition allows per unit) would be a multiple dwelling, not permitted in R-2.
Searched: the definitions above, DWELLING, TWO-FAMILY, ROOMING HOUSE / UNIT; a web search on 2026-10-27 found no City
record. Until answered: a two-family dwelling with more than one unrelated person in a unit (so possibly more than two
in the building) needs review in R-2, R-3 and RU; a one-family dwelling's limits (at most two) never reach "more than
two".

## 7. A home occupation always needs a person — A

The chart (p.2) marks "Home occupation" SP in every residential district, with §325-9B(1)(i): a special permit
"unless the home occupation meets all of the following criteria" (no stock or stored materials; no traffic or
parking beyond the residential use; no exterior alterations or display; no noise, vibration, smoke, dust or other
effects). Those, and §325-3B's conditions (a)-(e) and (g) (where it is carried on, at most two non-resident workers,
no signs, no nuisance, no extra traffic, vehicles and storage), are about how it runs, which a drawing can't show. So
Gordium's flag `home_occupation` always needs review once one is planned. Its size it can check (§8).

## 8. "No more than 25% of the dwelling unit and no more than a total of 500 indoor square feet" — A, with a B

HOME OCCUPATION (1)(f) (p.13). Over either limit it is no home occupation at all, so `home_occupation_size` does not
comply. "25% of the dwelling unit" is read as 25% of its floor area (B: the same sentence measures the 500 in
indoor square feet); to confirm with the architects.

## 9. Not covered

CR districts (no hand rulebook); rooming and boarding houses, cooperative households and the R-2c OCCUPANT count
(R-2c's own lot-size rules); occupancy of an accessory dwelling unit (ADUs are on the later list); the R-1 two-family
limits (§6.3).
