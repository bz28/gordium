# How Rhino talks to Gordium's code (2026-10-20)

**Purpose:** why all measuring and checking runs in Gordium's own Python, with Rhino only copying the model across and drawing the answer.\
**For:** engineers, and anyone choosing how the Rhino plugin is built.\
**Kept current by:** the engineer who changes how Rhino and the Python worker talk, in that PR.

**Amended 2026-11-06:** [How any design tool talks to Gordium's code](2026-11-06_hosts_talk_to_the_worker.md). The
decision below still holds; its "one code path" reason now means one checker for every design tool, with a second
geometry reader (Revit's) allowed only through the host conformance suite.

**Decision:** all measuring and checking runs in Gordium's own Python (3.12, the repo's packages). Inside
Rhino, a thin script only (1) copies the lot and building objects into a small temporary .3dm file and (2)
sends it, with the lot facts, to that Python running in the background, then shows what comes back.

**Why:**
- Rhino 8's built-in Python is 3.9; our packages need 3.12. Rewriting them for 3.9 would mean two versions of
  the rules code.
- **One code path** (for Rhino; a second tool's reader is guarded by the conformance suite since 2026-11-06). The same reader (rhino3dm, Rhino's own file library) measures a model on disk in CI and a
  live model in Rhino, so what the tests prove is what the architect gets.
- The checker stays plain code reading frozen rules (principle 3), and the measurements stay engineer-written
  code tested on real models (principle 6), all in one place.
- Speed: a 106 Ithaca Rd check takes about half a second once the background Python is running (median 0.47 s,
  re-timed 2026-11-18; about 0.2 s when this was decided, before egress, results grouping and the site-description
  round trip were added; the first check in a fresh worker takes about 1.3 s), fast enough to re-check after every edit.

**Considered:** rewriting the packages for Python 3.9 inside Rhino (two copies to keep in step); a C# plugin
(rewrite everything, or call Python anyway); measuring with RhinoCommon inside Rhino (a second measuring code
that CI can't run without Rhino).

**Cost:** the Rhino script needs the repo and its .venv on the same machine (fine for the MVP; a packaged
installer comes later).
