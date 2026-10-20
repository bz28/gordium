# How Rhino talks to Gordium's code (2026-10-20)

**Decision:** all measuring and checking runs in Gordium's own Python (3.12, the repo's packages). Inside
Rhino, a thin script only (1) copies the lot and building objects into a small temporary .3dm file and (2)
sends it, with the lot facts, to that Python running in the background, then shows what comes back.

**Why:**
- Rhino 8's built-in Python is 3.9; our packages need 3.12. Rewriting them for 3.9 would mean two versions of
  the rules code.
- **One code path.** The same reader (rhino3dm, Rhino's own file library) measures a model on disk in CI and a
  live model in Rhino, so what the tests prove is what the architect gets.
- The checker stays plain code reading frozen rules (principle 3), and the measurements stay engineer-written
  code tested on real models (principle 6), all in one place.
- Speed: a 106 Ithaca Rd check takes about 0.2 s once the background Python is running, fast enough to
  re-check after every edit.

**Considered:** rewriting the packages for Python 3.9 inside Rhino (two copies to keep in step); a C# plugin
(rewrite everything, or call Python anyway); measuring with RhinoCommon inside Rhino (a second measuring code
that CI can't run without Rhino).

**Cost:** the Rhino script needs the repo and its .venv on the same machine (fine for the MVP; a packaged
installer comes later).
