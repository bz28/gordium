"""The reference Python client of the checker (the worker): its two pipes, one request and its answer,
a long piece of work on its own thread, the session recorder (and its call recorder: every host_core call, for the
protocol's parity test), and when to restart the checker.

Moved here unchanged from rhino_logic.py, which still offers every name (so the Rhino plugin is
unchanged). Python 3.9 and the standard library only: Rhino 8 imports this into its own Python 3.9,
where none of the .venv's packages are installed."""

import functools
import inspect
import json
import math
import os
import queue
import re
import threading
import time
import types
from .lookup import MISSING
from .report import CANCELLING

__all__ = ['venv_python', 'code_fingerprint', 'restart_checker', 'Job', 'ASK_LIMIT_S', 'ASK_LIMITS_S', 'ask_limit',
    'CheckerOutOfStep', 'pipes', '_read_lines', '_write_lines', 'exchange', 'RECORD_ENV', 'Recorder', '_copy_file',
    'CALLS_ENV', 'NotPlain', 'MISSING_MARK', 'plain', 'unplain', 'with_tuples', '_Asked', 'CallRecorder', 'answer_for']


def venv_python(root, os_name):
    """Where the repo's virtual environment keeps Python: bin/python (Mac, Linux), Scripts\\python.exe (Windows)."""
    if os_name == "nt":
        return "\\".join((root, ".venv", "Scripts", "python.exe"))
    return "/".join((root, ".venv", "bin", "python"))


def code_fingerprint(packages_dir):
    """What the checker's code is now: every file under packages/ (code and the data it loads) with its size and
    time, as one text. The
    background checker is started again whenever this changes (an update while Rhino is open), so results never
    come from code that is no longer there."""
    import os
    found = []
    for root, dirs, files in os.walk(packages_dir):         # code and the data it loads (measures.yaml), not caches
        dirs[:] = sorted(d for d in dirs if d != "__pycache__" and not d.startswith(".") and not d.endswith(".egg-info"))
        for name in sorted(files):
            if not name.endswith((".pyc", ".pyo")) and not name.startswith("."):
                path = os.path.join(root, name)
                try:
                    st = os.stat(path)
                    found.append("%s:%d:%d" % (os.path.relpath(path, packages_dir), st.st_size, st.st_mtime_ns))
                except OSError:         # gone between listing and reading (an editor's temporary file): changed
                    found.append("%s:gone" % os.path.relpath(path, packages_dir))
    return "|".join(found)


def restart_checker(alive, started_with, now):
    """Whether to start the background checker again: it stopped, or the code changed since it started."""
    return not alive or started_with != now


class Job:
    """One piece of long work on its own thread, never Rhino's: work(step) returns the result; step(text) says what
    it is doing now. Rhino's thread only reads it (done, step, elapsed()), waits a moment for it (wait), and may
    cancel it: `stop` (run on the caller's thread) stops the process doing the work, and from then on the work's
    result is never used (outcome() says "cancelled" even if an answer still arrives)."""

    def __init__(self, work, step, stop=None, clock=time.monotonic):
        self.step, self.done, self.cancelled = step, False, False
        self.result = self.error = None
        self._stop, self._clock = stop, clock
        self.started = clock()
        self._thread = threading.Thread(target=self._run, args=(work,), daemon=True, name="gordium-job")
        self._thread.start()

    def say(self, text):
        if text and not self.cancelled:
            self.step = text

    def _run(self, work):
        try:
            self.result = work(self.say)
        except BaseException as e:            # noqa: BLE001  (kept for the caller, on its own thread)
            self.error = e
        finally:
            self.done = True

    def elapsed(self):
        return self._clock() - self.started

    def finished(self):
        """Nothing more to wait for: the work is done, or it was cancelled (its answer is dropped)."""
        return self.done or self.cancelled

    def wait(self, timeout):
        """Wait at most `timeout` s for the work; whether there is nothing more to wait for."""
        self._thread.join(timeout)
        return self.finished()

    def cancellable(self):
        return self._stop is not None and not self.finished()

    def cancel(self):
        """Stop the work (once; never after it is done; never work with no way to stop it, whose thread would go on
        reading the checker's answers: review round 2): True when it was stopped."""
        if not self.cancellable():
            return False
        self.cancelled = True
        self.step = CANCELLING
        if self._stop is not None:
            self._stop()
        return True

    def outcome(self):
        """("cancelled", None), ("error", the exception) or ("done", the result)."""
        if self.cancelled:
            return "cancelled", None
        if self.error is not None:
            return "error", self.error
        return "done", self.result


ASK_LIMIT_S = 60          # s: the longest the plugin waits for one answer (the first also starts Python, loads rules)
ASK_LIMITS_S = {"start": 120}   # s, per command that can take longer: the largest building, on a deep lot


def ask_limit(cmd):
    """How long the plugin waits for the checker's answer to one `cmd` request."""
    return ASK_LIMITS_S.get(cmd, ASK_LIMIT_S)


class CheckerOutOfStep(RuntimeError):
    """The checker's next line can't be trusted to be this request's answer: the plugin restarts the checker and
    shows nothing from it."""


def pipes(process):
    """The checker's two pipes, each served by its own thread: (sends, lines). Rhino's thread never reads or writes
    a pipe, so a checker that stops answering (or stops reading a large request) can never freeze Rhino; the
    plugin only puts on `sends` and waits on `lines` with a time limit (answer_for). Put None on `sends` to end
    the writer."""
    sends, lines = queue.Queue(), queue.Queue()
    threading.Thread(target=_read_lines, args=(process.stdout, lines), daemon=True,
                     name="gordium-reader-%s" % getattr(process, "pid", "")).start()
    threading.Thread(target=_write_lines, args=(process.stdin, sends, process), daemon=True,
                     name="gordium-writer-%s" % getattr(process, "pid", "")).start()
    return sends, lines


def _read_lines(stream, lines):
    """The reader thread: every line the checker writes, then None when it stops."""
    try:
        for line in stream:
            lines.put(line)
    except (OSError, ValueError):            # the pipe closed under it (the checker was stopped)
        pass
    finally:
        lines.put(None)


def _write_lines(stream, sends, process=None):
    """The writer thread: each request, in order, until None, the checker stops reading (then the reader sees it
    stop, or ask's time limit runs out), or the checker process ends (however it was stopped)."""
    try:
        while True:
            try:
                text = sends.get(timeout=1)
            except queue.Empty:
                if process is not None and process.poll() is not None:
                    return
                continue
            if text is None:
                return
            stream.write(text)
            stream.flush()
    except (OSError, ValueError):
        pass


def exchange(sends, lines, request, limit, on_step=None, record=None):
    """Send one request (a dict with its "id") and wait at most `limit` s for its answer (answer_for); each progress
    line before it goes to `on_step`. `record`: a Recorder that saves the request, its progress lines and its answer
    (the plugin passes one only when RECORD_ENV names a folder; None, the default, records nothing)."""
    if record is not None:
        return record.exchange(sends, lines, request, limit, on_step)
    sends.put(json.dumps(request) + "\n")
    return answer_for(lines, request["id"], limit, on_step)


RECORD_ENV = "GORDIUM_RECORD_SESSION"     # a folder: every request to the checker and its answer saved there


class Recorder:
    """Saves a session's traffic with the checker, for the replay test (design_checker/tests/test_replay.py): one
    line per request in `folder`/session.jsonl, {"n", "request", "steps", "reply"}, where "reply" is the answer
    line as the checker writes it (json.dumps of its reply: the line read back and written again gives the same
    text; None if no answer came) and "steps" its progress lines. The model file a
    request names is copied first, byte for byte, to files/<n>/<its own name> (its own name: the checker's answer
    quotes it), and the request records that copy's path relative to the folder; a report path is recorded the
    same way (the report itself is the checker's to write). Every request keeps its own copy of the model, so a long
    session takes room (one model's size per check). Off unless the plugin is started with RECORD_ENV set
    (`from_env`). Recording never stops a check: a recording that fails is noted in `failed` (the plugin says so
    once, on Rhino's thread: `take_failure`) and the exchange goes on unrecorded."""

    def __init__(self, folder, copy=None):
        self.folder = folder
        self.failed = None
        self._copy = copy or _copy_file
        self._lock = threading.Lock()
        self._n = None
        self._told = False

    @classmethod
    def from_env(cls, environ):
        folder = (environ.get(RECORD_ENV) or "").strip()
        return cls(folder) if folder else None

    def take_failure(self):
        """Why the recording failed, the first time it is asked after a failure (to say once), else None."""
        if self.failed is None or self._told:
            return None
        self._told = True
        return self.failed

    def _next(self):
        if self._n is None:             # a folder recorded into before: carry on after its last request (or its
            path = os.path.join(self.folder, "session.jsonl")      # last copied model, if that one's line was lost)
            n = 0
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    n = sum(1 for line in f if line.strip())
            files = os.path.join(self.folder, "files")
            if os.path.isdir(files):        # only the recorder's own folders (0001…; never "²" or "x")
                n = max([n] + [int(d) for d in os.listdir(files) if re.fullmatch(r"[0-9]+", d)])
            self._n = n                     # set only once worked out: a failure is tried again next time
        self._n += 1
        return self._n

    def _begin(self, request):
        with self._lock:
            n = self._next()
            saved = dict(request)
            for key in ("model", "report"):
                if saved.get(key):
                    rel = "files/%04d/%s" % (n, os.path.basename(str(saved[key])))
                    if key == "model":
                        target = os.path.join(self.folder, *rel.split("/"))
                        os.makedirs(os.path.dirname(target), exist_ok=True)
                        self._copy(str(saved[key]), target)
                    saved[key] = rel
            return {"n": n, "request": saved}

    def _end(self, entry, steps, reply):
        line = json.dumps(dict(entry, steps=steps, reply=None if reply is None else json.dumps(reply)))
        with self._lock:
            os.makedirs(self.folder, exist_ok=True)
            with open(os.path.join(self.folder, "session.jsonl"), "a", encoding="utf-8", newline="\n") as f:
                f.write(line + "\n")

    def exchange(self, sends, lines, request, limit, on_step=None):
        try:
            entry = self._begin(request)
        except Exception as e:                 # noqa: BLE001  (never a check lost to its recording)
            self.failed, entry = "%s: %s" % (type(e).__name__, e), None
        steps = []

        def step(text):
            steps.append(text)
            if on_step is not None:
                on_step(text)
        reply = None
        try:
            reply = exchange(sends, lines, request, limit, step)
            return reply
        finally:
            if entry is not None:
                try:
                    self._end(entry, steps, reply)
                except Exception as e:         # noqa: BLE001
                    self.failed = "%s: %s" % (type(e).__name__, e)


def _copy_file(source, target):
    with open(source, "rb") as a, open(target, "wb") as b:
        b.write(a.read())


# ---- the call recorder: every host_core call, with what went in and what came out ---------------------------------
#
# The worker serves host_core's functions as protocol commands (design_checker/protocol.py), and the parity test
# (design_checker/tests/test_protocol.py) proves each command's JSON answer is the in-process answer, on calls the
# plugin's own logic really made. CallRecorder saves those calls. Off unless asked for (CALLS_ENV, or a test run
# with tests/record_calls.py: design_checker/call_session.py records the headless session that way).

CALLS_ENV = "GORDIUM_RECORD_CALLS"        # a folder: every host_core call saved there, one line each


class NotPlain(Exception):
    """A value the protocol can't carry as it is (not a dict with text keys, list, tuple, text, true/false, null, or a
    finite number), so the call it was in is not recorded."""


MISSING_MARK = "$missing"     # lookup.MISSING (a key with no value, in a pending preview's undo list) on the wire:
#                               {"$missing": true}, the one object with this key (any other is refused)


def plain(value, path=(), tuples=None, sets=None):
    """`value` as JSON would carry it, every tuple a list (its place added to `tuples`, a list of paths, when given),
    every set of text or numbers a sorted list when `sets` (a list of paths, likewise) is given (the model's ids),
    lookup.MISSING as {"$missing": true}, or NotPlain. Never a value quietly changed: a dict key that isn't text, NaN
    or infinity, any other object, a dict of its own with the "$missing" key, refused."""
    if value is MISSING:
        return {MISSING_MARK: True}
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        raise NotPlain("%s at %s" % (value, list(path)))
    if type(value) in (list, tuple):
        if type(value) is tuple and tuples is not None:
            tuples.append(list(path))
        return [plain(v, path + (i,), tuples, sets) for i, v in enumerate(value)]
    if type(value) in (set, frozenset) and sets is not None:
        if not all(isinstance(v, str) for v in value) and not all(
                isinstance(v, (int, float)) and not isinstance(v, bool) for v in value):
            raise NotPlain("a set of mixed or other values at %s" % (list(path),))
        sets.append(list(path))
        return [plain(v, path + (i,), tuples, sets) for i, v in enumerate(sorted(value))]
    if type(value) is dict:
        if not all(isinstance(k, str) for k in value):
            raise NotPlain("a key that isn't text at %s" % (list(path),))
        if MISSING_MARK in value:
            raise NotPlain("%r is the protocol's own key (lookup.MISSING), at %s" % (MISSING_MARK, list(path)))
        return {k: plain(v, path + (k,), tuples, sets) for k, v in value.items()}
    raise NotPlain("a %s at %s" % (type(value).__name__, list(path)))


def unplain(value):
    """`value` as JSON brought it, with each {"$missing": true} lookup.MISSING again (plain, the other way)."""
    if type(value) is dict:
        if len(value) == 1 and value.get(MISSING_MARK) is True:      # exactly the mark ({"$missing": 1} is not)
            return MISSING
        return {k: unplain(v) for k, v in value.items()}
    if type(value) is list:
        return [unplain(v) for v in value]
    return value


def with_tuples(value, paths, kind=tuple):
    """`value` (as `plain` gave it) with the lists at `paths` made tuples again (or `kind`: set), as the caller had
    them."""
    for path in sorted(paths, key=len, reverse=True):          # the deepest first, so a path above still finds it
        if not path:
            value = kind(value)
            continue
        holder = value
        for key in path[:-1]:
            holder = holder[key]
        holder[path[-1]] = kind(holder[path[-1]])
    return value


class _Asked:
    """A callable argument (a question to the architect: `ask`) seen through: each call's arguments and answer
    noted, the answer passed on unchanged."""

    def __init__(self, fn):
        self.fn, self.calls, self.raised = fn, [], False

    def __call__(self, *args):
        try:
            answer = self.fn(*args)
        except BaseException:
            self.raised = True            # (Esc at the question: a call no host can send, so not recorded)
            raise
        self.calls.append([list(args), answer])
        return answer


class CallRecorder:
    """Saves every call of host_core's functions (`install`) to `folder`/calls-<process>.jsonl, one line each:
    {"fn": "start_box.box_rows", "args": {name: value, ...} (as passed: defaults not filled in), "tuples": {name:
    [paths of the tuples in it]}, "sets": {name: [paths of its sets, each recorded as a sorted list]}, "result" or "raised" ([type, words]), "mutated": {name: value after} (an argument
    the call changed in place), "asked": {name: [[question args, answer], ...]} (a callable argument's calls)}.
    Calls inside calls are saved too (an edit plan is decided inside apply_lookup); a call made again exactly as
    before is saved once. Nothing is saved for a call any
    of whose values the protocol can't carry (NotPlain: counted in `skipped`), or while anything in host_core is
    swapped out (a test's monkeypatch: the answer is then not host_core's own; counted too). Recording never
    changes a call: the function gets the arguments it was given (a callable one through _Asked, which passes each
    call on and its answer back unchanged), and its answer or error goes back."""

    def __init__(self, folder):
        self.folder = folder
        self.skipped = {}
        self._lock = threading.Lock()
        self._local = threading.local()
        self._modules = ()
        self._seen = []
        self._lines = set()          # each different call saved once

    @classmethod
    def from_env(cls, environ):
        folder = (environ.get(CALLS_ENV) or "").strip()
        return cls(folder) if folder else None

    def install(self, modules, also=(), only=None):
        """Wraps every function `modules` define and list in __all__ (or only those named in `only`, as
        "start_box.box_rows"), in place: in each of `modules` and `also` (rhino_logic, which offers the same names)
        every name bound to it is bound to the wrapper instead."""
        found = []
        for module in modules:
            if module.__name__ == __name__:      # (this module: the recorder's own helpers, the client's pipes)
                continue
            for name in module.__all__:
                fn = vars(module)[name]
                label = module.__name__.split(".")[-1] + "." + name
                if isinstance(fn, types.FunctionType) and fn.__module__ == module.__name__ and \
                        (only is None or label in only):
                    found.append((label, fn))
        for label, fn in found:
            wrapper = self._wrap(label, fn)
            for module in tuple(modules) + tuple(also):
                for key, value in list(vars(module).items()):
                    if value is fn:
                        vars(module)[key] = wrapper          # (the module's own dict: past rhino_logic's refusal)
        self._modules = tuple(modules)
        self._seen = [(vars(m), dict(vars(m))) for m in self._modules]
        return len(found)

    def _untouched(self):
        """Whether every name in host_core is bound as it was at install (no test swapped one)."""
        return all(len(now) == len(then) and all(now.get(k, self) is v for k, v in then.items())
                   for now, then in self._seen)

    def _skip(self, reason):
        with self._lock:
            self.skipped[reason] = self.skipped.get(reason, 0) + 1

    def _wrap(self, label, fn):
        signature = inspect.signature(fn)
        recorder = self

        @functools.wraps(fn)
        def recorded(*args, **kwargs):
            local = recorder._local
            depth = getattr(local, "depth", 0)
            if depth == 0:
                local.clean = recorder._untouched()
            local.depth = depth + 1
            try:
                if not local.clean:
                    recorder._skip("host_core swapped by a test")
                    return fn(*args, **kwargs)
                return recorder._call(label, fn, signature, args, kwargs)
            finally:
                local.depth = depth
        return recorded

    def _call(self, label, fn, signature, args, kwargs):
        try:
            bound = signature.bind(*args, **kwargs)
        except TypeError:
            return fn(*args, **kwargs)                   # (its own error, raised by the call itself)
        asked = {}
        for name, value in list(bound.arguments.items()):
            if callable(value):
                asked[name] = bound.arguments[name] = _Asked(value)
        try:
            tuples, sets, before = {}, {}, {}
            for name, value in bound.arguments.items():
                if name not in asked:
                    tuples[name], sets[name] = [], []
                    before[name] = plain(value, (), tuples[name], sets[name])
        except NotPlain:
            before = None
        try:
            result = fn(*bound.args, **bound.kwargs)
        except BaseException as e:           # (Esc at a question: KeyboardInterrupt or the plugin's own Cancelled)
            self._end(label, before, (tuples, sets), bound, asked, raised=[type(e).__name__, str(e)])
            raise
        self._end(label, before, (tuples, sets), bound, asked, result=result)
        return result

    def _end(self, label, before, kinds, bound, asked, **outcome):
        if before is None:
            self._skip(label + ": an argument the protocol can't carry")
            return
        if any(a.raised for a in asked.values()):
            self._skip(label + ": a question it asked raised")
            return
        try:
            tuples, sets = kinds
            entry = {"fn": label, "args": before, "tuples": {k: v for k, v in tuples.items() if v}}
            if any(sets.values()):
                entry["sets"] = {k: v for k, v in sets.items() if v}
            if "result" in outcome:
                entry["result"] = plain(outcome["result"])
            else:
                entry["raised"] = outcome["raised"]
            after = {k: plain(v, (), None, []) for k, v in bound.arguments.items() if k not in asked}
            mutated = {k: v for k, v in after.items() if v != before[k]}
            if mutated:
                entry["mutated"] = mutated
            if asked:
                entry["asked"] = {k: plain(a.calls) for k, a in asked.items()}
            line = json.dumps(entry, allow_nan=False)      # (keys in their order: host_core's words can follow it)
        except (NotPlain, ValueError):
            self._skip(label + ": an answer the protocol can't carry")
            return
        with self._lock:
            if line in self._lines:
                return
            self._lines.add(line)
            os.makedirs(self.folder, exist_ok=True)
            with open(os.path.join(self.folder, "calls-%d.jsonl" % os.getpid()), "a", encoding="utf-8",
                      newline="\n") as f:
                f.write(line + "\n")


def answer_for(lines, request_id, limit, on_step=None, clock=time.monotonic):
    """The checker's answer to request `request_id`, from `lines` (a queue the plugin's reader thread fills with
    every line the checker writes, then None when it stops); None if it stopped. This request's progress lines
    ({"id", "step"}, sent before its answer) go to `on_step`. Raises CheckerOutOfStep when the answer doesn't come
    within `limit` seconds of asking (progress lines don't extend it), when a line isn't this request's, or isn't
    an answer: then later lines may belong to earlier requests, so the plugin restarts the checker rather than ever
    showing an earlier check's result as this one's."""
    deadline = clock() + limit
    while True:
        try:
            line = lines.get(timeout=max(0.0, deadline - clock()))
        except queue.Empty:
            raise CheckerOutOfStep("the Gordium checker gave no answer in %d s, so it was restarted" % limit)
        if line is None:
            return None
        try:
            answer = json.loads(line)
        except ValueError:
            answer = None
        if not isinstance(answer, dict) or answer.get("id") != request_id:
            raise CheckerOutOfStep("the Gordium checker's answer didn't match the request, so it was restarted and "
                                   "nothing from it is shown")
        if "step" in answer and "ok" not in answer:      # a progress line: what it is doing now
            if on_step is not None and not answer.get("again"):   # a repeat says only that it is still working
                on_step(str(answer["step"]))
            continue
        return answer
