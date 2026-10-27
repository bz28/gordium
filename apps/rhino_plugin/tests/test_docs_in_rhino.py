"""The one way the in-Rhino tests open documents (run in Rhino, imported by them; not a CI test).

    with TestDocs("ui_flow") as docs:
        doc = docs.open("Large Objects - Feet")      # a fresh copy of Rhino's own template, as the active document
        ...                                          # the test
    # every document this run opened is closed, unsaved, except the last one (left as the active document)

Each test document is a copy under <temp>/gordium_test_docs/, one reused file per test and template (never a new
timestamped file per run). When a run starts, any test document an earlier run left open is reported and closed.
Only documents under that folder are ever closed. RhinoCommon has no close call that works on a document with a
window here (RhinoDoc.Dispose doesn't close it; a document keeps its last view): the document's window is closed
through Eto, as its close button does, after marking the copy unmodified, so no "save changes?" question can come
up. Never an interactive command: `_-Close` waits at the command line and blocks Rhino."""
import glob
import os
import shutil
import tempfile

import Rhino

FOLDER = os.path.join(tempfile.gettempdir(), "gordium_test_docs")
BUNDLED = ("/Applications/Rhino 8.app/Contents/Frameworks/RhCore.framework/Versions/A/Resources/en.lproj/"
           "Template Files")


def _mine(doc):
    return os.path.realpath(doc.Path or "").startswith(os.path.realpath(FOLDER) + os.sep)


def close(doc):
    """Close one test document, unsaved (only one of ours)."""
    if doc is None or not _mine(doc):
        return False
    doc.Modified = False
    window = Rhino.UI.RhinoEtoApp.MainWindowForDocument(doc)
    if window is None:
        return False
    window.Close()
    return True


def leftovers():
    return [d for d in Rhino.RhinoDoc.OpenDocuments() if _mine(d)]


def template(name):
    """Rhino's own template file by name ("Small Objects - Millimeters")."""
    for folder in (Rhino.ApplicationSettings.FileSettings.TemplateFolder, BUNDLED):
        path = os.path.join(folder or "", name + ".3dm")
        if os.path.exists(path):
            return path
    found = glob.glob(os.path.join(BUNDLED, name + ".3dm"))
    if not found:
        raise RuntimeError("Rhino template not found: " + name)
    return found[0]


class TestDocs:
    def __init__(self, test):
        self.test, self.opened, self.left_over = test, [], []

    def __enter__(self):
        os.makedirs(FOLDER, exist_ok=True)
        for doc in leftovers():                       # an earlier run's: reported, then closed
            self.left_over.append(doc.Path)
            close(doc)
        return self

    def open(self, template_name):
        """A fresh copy of the template as the active document, one reused file per test and template."""
        path = os.path.join(FOLDER, (self.test + "_" + template_name).replace(" ", "_") + ".3dm")
        for doc in list(Rhino.RhinoDoc.OpenDocuments()):
            if os.path.realpath(doc.Path or "") == os.path.realpath(path):
                close(doc)
        shutil.copy(template(template_name), path)
        Rhino.RhinoDoc.Open(path)
        doc = Rhino.RhinoDoc.ActiveDoc
        if doc is None or os.path.realpath(doc.Path or "") != os.path.realpath(path):
            raise RuntimeError("the opened test document isn't the active one: " + str(doc.Path if doc else None))
        self.opened.append(doc)
        return doc

    def __exit__(self, *exc):
        for doc in self.opened[:-1]:                  # the last stays, as the active document
            try:
                close(doc)
            except Exception:
                pass
        return False
