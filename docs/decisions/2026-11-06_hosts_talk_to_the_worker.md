# How any design tool talks to Gordium's code (2026-11-06)

**Purpose:** why every design tool (Rhino now, Revit later) sends Gordium the same site description and calls the same worker commands, and how a second geometry reader is kept honest.\
**For:** engineers building a design-tool add-in, and anyone choosing how Gordium reaches Revit.\
**Kept current by:** the engineer who changes what a design tool sends Gordium or how it is tested, in that PR.

This amends [How Rhino talks to Gordium's code (2026-10-20)](2026-10-20_rhino_talks_to_python.md). That
decision still holds: all measuring and checking runs in Gordium's own Python. What changes is its "one reader"
reason, now that a second design tool is coming.

**Decision:**

1. **Every design tool (a host) speaks one language to one checker.** It sends the
   [site description](../protocol/site_description_v1.md) (`gordium.site/1`: the lot, each building as flat faces,
   the ground, what couldn't be sent, what was left out) and calls the
   [worker protocol](../protocol/worker_protocol_v1.md)'s commands (`check_site`, `start_site`, the session
   commands). The measuring, the rules and the answers are the worker's, the same for every host. Rhino already
   takes this path: its `check` makes a site description, sends it through JSON text and back, and checks that.
2. **A host may read its own model's geometry** (a second reader: Revit's add-in, in C#, deciding which faces are
   flat and which curved, what is left out), **guarded by the [host conformance suite](../../test_data/host_conformance/README.md)**
   (Ben, 2026-11-05). On fixed scenes (a curved wall, an open solid, a block, a garage left out, millimetres,
   survey coordinates, a corner lot, an edit…), the host's description must match the expected one (every point
   within a millionth of a foot, the same ids, problem codes and left-out objects) and give exactly the
   hand-worked verdicts. A host that sends fewer problems than expected fails, whatever the verdicts. A host that
   can't run on the Mac records its descriptions once on its own machine (`recorded/<host>/`), and CI checks them
   on every push.
3. **Each check's site description is kept beside its report** (`<report name>.site.json`, Ben, 2026-11-06), so any
   result can be traced to exactly what the host sent and worked out again with the same lot facts, whichever host
   sent it.

**Why:**
- **Never a false pass, whichever tool.** The description is strict (anything unknown is refused, never skipped),
  and the conformance suite makes each reader prove, on the cases where readers go wrong, that it reports what it
  can't read. The old reason, "the same reader in CI and in Rhino", becomes "the same checker for every reader, and
  every reader tested on the same scenes in CI".
- **One checker.** The rules and the measuring are never written twice (principles 3 and 6); a Revit add-in adds a
  reader, not a second Gordium.
- **Testable without Revit.** Revit only runs on Windows with a licence; the recordings let the Mac and CI check
  its reader all the same.
- **Revit already knows its geometry.** Its API says which faces are planar and gives each element a stable id
  (UniqueId), which is what the description needs.

**Considered:**
- **Revit writes a .3dm with Rhino3dm .NET, and the existing reader reads it.** One reader stays, on paper. But
  turning Revit geometry into Rhino surfaces is itself a reader: which faces are flat or curved, and what is left
  out, would be decided inside a format conversion, out of sight. It adds a dependency, the Revit ids have to be
  carried through user strings, and the conversion still needs a test like this suite to trust it.
- **IFC export, read in Python.** Revit's IFC export depends on its export settings, can turn curved walls into
  many small flat faces without saying so (a curved wall then looks measurable: a false-pass risk), and takes
  seconds to minutes on a real model, too slow to check after every edit. It also needs an IFC reader in Python,
  a new dependency to pin.
- **pyRevit.** Python inside Revit, but still a second reader in Revit's API, so no gain on what this suite
  guards, and a less usual way to ship an add-in to firms than a C# add-in.
- **Rhino.Inside.Revit.** Rhino running inside Revit would keep Rhino's reader, but every Revit seat would need a
  Rhino licence and install, a heavy ask for firms that work only in Revit.

**Cost:**
- Two readers to keep in step. Each change to the site description, a scene or the measuring means the Revit
  add-in records its scenes again on Windows.
- The suite proves only what its scenes draw. A case found later that a host misreads becomes a new scene, and
  every host records it.
- A kept site description is model geometry Gordium stores beside each report.
