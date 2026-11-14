# ifc_reading

Reads an IFC building model (the open file format most design tools export: ArchiCAD, Revit, Vectorworks) into
Gordium's [interior description](../../docs/interior/interior_description_format.md) (`gordium.interior/1`), so
egress can be measured on real building models on a Mac, before the Revit add-in exists. Plain code, no AI: every
value is the model's own, or it is left out with the reason why.

```
python -m ifc_reading <model.ifc> <out.yaml>        # the interior description
python -m model_measurement.interior <out.yaml>     # its egress measures (inches, square feet)
python -m ifc_reading --check                       # CI: each committed description matches a fresh read
```

**Install.** It needs [ifcopenshell](https://ifcopenshell.org) 0.9.0.post1 (LGPL-3.0; about 44 MB to download, 160 MB
installed), an optional
extra that the checker never needs: `pip install -e ".[ifc]"`. Everything else in Gordium installs and runs without
it, and this package's tests are skipped where it isn't installed (CI's `ifc` job installs it and runs them).

**Memory.** Reading the KIT test house (2.6 MB, below) peaks at 147 MB for the whole Python process (macOS
`/usr/bin/time -l`, 2026-11-13): 48 MB for Python with ifcopenshell loaded, 17 MB more to open the file, the rest
building each room's, window's and opening's shape. It takes under 2 seconds on an M2 Mac.

## What it reads, and what it leaves out

Lengths are converted from the file's own length unit (its `IfcUnitAssignment`: metres, millimetres, feet…) to
metres; the description says `units: m`. Areas likewise, from its area unit. A file stating no single length unit
is refused.

Each part keeps `not_given` (every key of the format it couldn't fill, with the reason) and `ifc` (where each value
came from: the IFC entity, its STEP line number, its GlobalId, the property or quantity read). `source` at the end
records the file (name, SHA-256 fingerprint, schema, unit) and what wasn't read at all.

### Rooms (`IfcSpace`)

| Key | Read from | Left out when |
|---|---|---|
| `sleeping` | the room's words (below), or the `Gordium_Egress.Sleeping` flag | the words don't settle it |
| `floor_elevation` | the space's base (its body's lowest point) + its `FinishFloorHeight` quantity | `FinishFloorHeight` isn't given |
| `floor` | the outline of the space's underside | the underside isn't one level outline, or the outline's area is more than the space's `NetFloorArea` quantity, or that quantity isn't given |
| `ceiling_height` | the `FinishCeilingHeight` quantity (the lower of it and the space's top, above the finished floor) | it isn't given, the floor elevation isn't known, or the space's top isn't level |

**Sleeping room or not: only from words or a flag, never from size.** The room's words are taken from its IFC
`LongName`, `Name`, `ObjectType` and classification names (Unicode-normalised, so "Gästezimmer" reads the same
however its "ä" is stored) and looked up whole in [`room_words.yaml`](ifc_reading/room_words.yaml) (English and
German). A sleeping word (bedroom, nursery, Schlafzimmer) and no word against it → `sleeping: true`. Only words
for rooms that aren't slept in (bath, kitchen, hall, living, Küche), with at most *neutral* ones ("room", "No.")
→ `false`. Anything else → `sleeping` is left out: an *ask* word (office, den, loft, gallery, which a code official
may count as a sleeping room), both kinds, no listed word, or a word the table doesn't know beside a not-sleeping
one ("Elternzimmer + Bad", a parents' room with its bath: the unknown word may mean bedroom). The format then
reads none of the rooms (a bedroom nobody labelled is never quietly not a bedroom), so every sleeping-room rule
says **needs review** until the architect says. The architect says by giving the space a property set
`Gordium_Egress` with `Sleeping` true or false. True always counts. False settles an ask or unknown word (that is
what it is for), but not a room whose name says it is a sleeping room: a bedroom flagged false is left unknown, so
a slip is caught rather than a bedroom missed. A flag that is there but isn't true or false (the text "TRUE",
"Yes") is never left to the name: the room is unknown, with the value shown.

**Units of a stated number.** A quantity or property may carry its own unit (IFC lets each `IfcQuantityArea`,
`IfcQuantityLength` or property value name one); it is converted by that unit, otherwise by the file's. One stated
in a unit of the wrong kind (an area in a length unit) is left out, with the reason. A quantity stated twice (an
export holding both IFC4's `Qto_SpaceBaseQuantities` and IFC2x3's `BaseQuantities`) is read only if both agree,
never the first one found. A flag stored as something other than a single value (an enumerated or list value)
is never taken as absent: its part is left unknown, with what was found. A flag stated twice on the same element
(two `Gordium_Egress` sets, say) must agree likewise; the element's own flag overrides its type's (IFC's
inheritance: a window type marked one way, one window of it marked the other).

**Why the floor outline needs the net floor area.** The format wants the finished floor's outline, inside the
finished walls. An IFC space can be drawn to the rough wall or the wall's centre; IFC4's `NetFloorArea` is the
space's "usable floor area". An outline larger than it may be too big, and a bedroom's floor area (a minimum) would
be too much, so the outline is left out. In the KIT house ArchiCAD reduces most rooms' net area by 3% for plaster:
their outlines are left out, the kitchen's (net = drawn) is kept.

**Why the floor and ceiling need their quantities.** IFC4 defines a space's `Height` as "from base slab without
flooring to ceiling without suspended ceiling", `FinishFloorHeight` as "from base slab without flooring to the
flooring height" and `FinishCeilingHeight` as "from top of flooring to the bottom of the suspended ceiling". So a
space's base is the slab, not the finished floor, and its top is the slab above, not the finished ceiling. Without
those quantities the finished floor and ceiling aren't known. A sloped or stepped ceiling isn't read yet.

### Openings (`IfcWindow`, and exterior `IfcDoor`)

Every window is an opening; so is a door that bounds exactly one room (an outside door) or is marked as an escape
opening. A door's id as an opening is its GlobalId + `/opening` (ids are unique in a description, and the same
door is also in `doors`).

| Key | Read from | Left out when |
|---|---|---|
| `room` | the room its space boundary (`IfcRelSpaceBoundary`) names | no boundary names one, or it bounds more than one |
| `escape` | `Gordium_Egress.EscapeOpening`, or a window's `Pset_WindowCommon.FireExit` ("an exit window in accordance to the national building code") | never: not marked (or marked with something other than true/false, recorded in `escape_from`) is `false`. Only an opening the architect marks is checked (Ben, 2026-11-12); a bedroom with none marked fails, never passes |
| `operation` | a single-panel window's `IfcWindowPanelProperties.OperationType` (side-hung → casement, top-hung → awning, bottom-hung → hopper, sliding horizontal → horizontal slider, fixed → fixed…); a door's operation type (single swing → side-hinged door, sliding → sliding door) | a window of more than one panel; sliding vertical (single- or double-hung: IFC doesn't say); not defined |
| `frame` | a rectangular, upright, single-panel window: its `OverallWidth` × `OverallHeight` at its origin, less its lining's `LiningThickness` all round (IFC4: the overall size is "a bounding box, enclosing the window opening") | the window isn't rectangular (a round window's bounding box isn't its opening), isn't upright, has a mullion or transom or more than one panel, has no lining thickness, or its body or the opening it fills disagree with its stated size; every door |
| `hinged`, `sashes`, `stated_clear`, `ground_outside` | never | not in IFC: how far a sash opens, where open sashes stand, the maker's clear opening, the ground outside |

The frame's `u` runs along the window's own x axis from its origin. The frame is the same either way along it, and
nothing the reader gives depends on which way is "left" seen from the room.

So no escape opening's clear opening is measured from IFC alone: a hinged or sliding window needs its sash data,
and the others the maker's clear opening. Each opening's `ifc` still records its overall size, the bottom of its
opening (`opening_bottom`) and, where the room's floor is known, that bottom's height above the floor.

### Doors (`IfcDoor`)

`exit` from `Gordium_Egress.ExitDoor` or `Pset_DoorCommon.FireExit`; left out when the model says neither, or
says something other than true or false (then
the format reads no doors, and the exit-door rules need review). `operation` from the door's operation type. The
stops, hinge pin, closed leaf, threshold and head stop aren't in IFC, so the clear width and height aren't
measured.

### Stairs and guards

Not read: the description leaves out `stairs` and `guards`, so every stair and guard rule needs review. Stairs
come from the Revit add-in, since an IFC export doesn't give each nosing's place (Revit's IFC export is weakest for
stairs). What the model says about each `IfcStairFlight` (risers, treads, riser height, tread length, from its
attributes or `Pset_StairFlightCommon`) is kept under `source.stair_flights`, each number with where it came from.

## The test house

[`test_data/ifc_models/ac20_fzk_haus/`](../../test_data/ifc_models/ac20_fzk_haus/README.md): KIT's FZK-Haus, a
two-storey house exported from ArchiCAD 20 as IFC4. Its committed description is
`AC20-FZK-Haus_interior.yaml`; `tests/test_fzk_haus.py` checks values worked out by hand from the file's own lines
(the STEP line numbers are in each test), and `tests/test_made_up_models.py` checks small models built for each
rule (feet, millimetres, a single-panel window, a mullion, a roof window, flags).
