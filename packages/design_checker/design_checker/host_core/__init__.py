"""The checker's host-neutral helpers: what the Rhino plugin (and later a Revit add-in) asks about a site, with no
CAD program in them. Each module is plain Python 3.9 using only the standard library, because Rhino 8 imports
them into its own Python 3.9 (through rhino_logic.py, which offers every name here unchanged).

  place          the place checked (place.json)
  streets        which lot edges face a street
  facts          the facts the architect states
  lookup         an address lookup's answer, saved addresses
  start_box      the start box's rows, buttons and reset
  edits          the start box's model edits: one transaction, decided as edit plans
  freshness      whether the results shown are current, the undo steps' names
  report         the report's and long work's words
  panel_words    the panel's words
  context        the neighbourhood around a looked-up lot
  worker_client  the reference client of the checker (its pipes, one request and its answer, a Job, the recorder)
"""
