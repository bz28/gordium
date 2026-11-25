using System.Diagnostics;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Channels;

namespace Gordium.Worker;

/// <summary>
/// One running worker (<c>python -m design_checker serve</c>) and the protocol it speaks
/// (docs/protocol/worker_protocol_v1.md): one JSON request per line in, one answer per line out.
/// </summary>
/// <remarks>
/// <para>Requests go one at a time, each with the next id. Any answer that can't be trusted to be this request's
/// (not JSON, another id, a field missing) stops the worker, as does a timeout, a cancel or a crash: its later lines
/// might belong to an earlier request, and an earlier check shown as this one's would be a false pass. After that
/// every call throws <see cref="WorkerStoppedException"/> (<see cref="IsStopped"/> says so): start a new client; the
/// worker keeps nothing between requests, so nothing is lost. <see cref="WorkerRefusedException"/>,
/// <see cref="PartRefusedException"/> and <see cref="AnswerMissingException"/> leave the worker serving.</para>
/// <para>What it throws: a <see cref="WorkerException"/> for anything the worker did or didn't answer;
/// <see cref="OperationCanceledException"/> when the caller cancels (the worker is then stopped);
/// <see cref="ArgumentException"/> for a request it won't send (a request's own field, a value JSON can't carry,
/// a command it doesn't know), before anything is sent.</para>
/// <para>Requests are written as UTF-8 without a byte-order mark (the worker refuses one).</para>
/// </remarks>
public sealed class WorkerClient : IDisposable
{
    private static readonly UTF8Encoding Utf8 = new(encoderShouldEmitUTF8Identifier: false, throwOnInvalidBytes: true);

    private readonly WorkerOptions _options;
    private readonly Process _process;
    private readonly Channel<string> _lines = Channel.CreateUnbounded<string>();
    private readonly Queue<string> _log = new();
    private readonly SemaphoreSlim _one = new(1, 1);
    private long _nextId;
    private string? _stopped;            // why the worker was stopped; null while it serves
    private Exception? _readFailure;     // what ended the reader, when it wasn't the worker closing its output

    /// <summary>What the worker said about itself at <c>hello</c>.</summary>
    public WorkerAbout About { get; private set; } = null!;

    /// <summary>The worker's process id.</summary>
    public int ProcessId => _process.Id;

    /// <summary>Whether the worker was stopped (after a failure, or <see cref="Dispose"/>).</summary>
    public bool IsStopped => _stopped is not null;

    private WorkerClient(WorkerOptions options)
    {
        _options = options;
        var info = new ProcessStartInfo(options.PythonPath)
        {
            WorkingDirectory = options.WorkingDirectory,
            UseShellExecute = false,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
        };
        foreach (var a in options.Arguments)
            info.ArgumentList.Add(a);
        foreach (var (k, v) in options.Environment)
            info.Environment[k] = v;
        _process = new Process { StartInfo = info };
    }

    /// <summary>Starts the worker and says <c>hello</c>: refuses a worker that doesn't speak protocol 1.x and
    /// gordium.site/1. Throws a <see cref="WorkerException"/> (the worker stopped) when it can't.</summary>
    public static async Task<WorkerClient> StartAsync(WorkerOptions options, CancellationToken cancel = default)
    {
        ArgumentNullException.ThrowIfNull(options);
        var client = new WorkerClient(options);
        try
        {
            if (!client._process.Start())
                throw new WorkerUnavailableException("The Gordium checker didn't start");
        }
        catch (System.ComponentModel.Win32Exception e)
        {
            client._stopped = "it didn't start";
            client._process.Dispose();
            throw new WorkerUnavailableException($"The Gordium checker couldn't be started with {options.PythonPath}: {e.Message}", e);
        }
        client.StartReaders();
        try
        {
            client.About = await client.HelloAsync(options.StartTimeout, cancel).ConfigureAwait(false);
        }
        catch
        {
            client.Dispose();
            throw;
        }
        return client;
    }

    private void StartReaders()
    {
        var output = new StreamReader(_process.StandardOutput.BaseStream, Utf8, detectEncodingFromByteOrderMarks: false);
        _ = Task.Run(async () =>
        {
            try
            {
                while (await output.ReadLineAsync().ConfigureAwait(false) is { } line)
                    await _lines.Writer.WriteAsync(line).ConfigureAwait(false);
            }
            catch (Exception e) when (e is IOException or ObjectDisposedException or DecoderFallbackException)
            {
                if (e is DecoderFallbackException)
                    _readFailure = e;
            }
            finally
            {
                _lines.Writer.TryComplete();
            }
        });
        // the worker's log: always read, or a full stderr pipe would stop the worker mid-answer
        var errors = new StreamReader(_process.StandardError.BaseStream, new UTF8Encoding(false, false),
                                      detectEncodingFromByteOrderMarks: false);       // a log: never refused
        _ = Task.Run(async () =>
        {
            try
            {
                while (await errors.ReadLineAsync().ConfigureAwait(false) is { } line)
                    lock (_log)
                    {
                        _log.Enqueue(line);
                        while (_log.Count > _options.LogLines)
                            _log.Dequeue();
                    }
            }
            catch (Exception e) when (e is IOException or ObjectDisposedException) { }
        });
    }

    // ---- the typed commands ---------------------------------------------------------------------------------------

    /// <summary><c>hello</c>: the protocol, the site description version and the worker's fingerprints.</summary>
    public Task<WorkerAbout> HelloAsync(CancellationToken cancel = default) => HelloAsync(_options.RequestTimeout, cancel);

    private async Task<WorkerAbout> HelloAsync(TimeSpan timeout, CancellationToken cancel)
    {
        var answer = await ExchangeAsync("hello", new JsonObject(), timeout, cancel).ConfigureAwait(false);
        return Guard(() => WorkerAbout.Parse(answer.Result, "result"));
    }

    /// <summary><c>check_site {site, facts, report?, extras?, today?}</c>: the check of a site description.</summary>
    /// <param name="site">The site description (gordium.site/1).</param>
    /// <param name="facts">The lot facts the architect states.</param>
    /// <param name="report">Where to write the zoning report (.xlsx), or null for none.</param>
    /// <param name="extras">What the host adds to the check (as the Rhino command's <c>extras</c>), or null.</param>
    /// <param name="today">The day of the check as YYYY-MM-DD, the place's own day (how old a saved address lookup
    /// is), or null: then no lookup counts as recent and the overlays row stays. The checker never reads the clock.</param>
    /// <param name="interior">The house's inside (<c>gordium.interior/1</c>, docs/interior/interior_description_format.md),
    /// which the place's inherited laws (egress, for Ithaca) are checked on; null for none (they then wait). Sent only
    /// to a worker whose <c>hello</c> said protocol 1.2 or later: an older one would ignore it and say egress waits, as
    /// if no rooms were drawn, so with an older worker this throws <see cref="WorkerVersionException"/> and sends
    /// nothing (the worker keeps running).</param>
    /// <param name="cancel">Cancels the wait; the worker is then stopped.</param>
    /// <param name="silence">With a value, the worker is asked for its progress lines and stopped only when it says
    /// nothing for this long (WorkerTimeoutException with Silent); null: one limit for the whole answer, as before.</param>
    /// <param name="step">Told each progress line's words as it comes (with <paramref name="silence"/> only).</param>
    /// <param name="total">With <paramref name="silence"/>: the longest the whole answer may take, whatever the worker
    /// says meanwhile (then WorkerTimeoutException, not Silent); null: no ceiling beyond the silence.</param>
    public async Task<CheckResult> CheckSiteAsync(JsonNode site, JsonNode facts, string? report = null,
                                                  JsonNode? extras = null, string? today = null,
                                                  JsonNode? interior = null, CancellationToken cancel = default,
                                                  TimeSpan? silence = null, IProgress<string>? step = null, TimeSpan? total = null)
    {
        ArgumentNullException.ThrowIfNull(site);
        ArgumentNullException.ThrowIfNull(facts);
        if (interior is not null && About.Minor < Protocol.InteriorMinor)
            throw new WorkerVersionException(
                $"This Gordium checker speaks protocol {About.Protocol}; checking egress on the house's inside needs " +
                $"1.{Protocol.InteriorMinor} or later: update the checker (an older one would say egress waits, as if " +
                "no rooms were drawn)");
        var fields = new JsonObject { ["site"] = site.DeepClone(), ["facts"] = facts.DeepClone() };
        if (report is not null)
            fields["report"] = report;
        if (extras is not null)
            fields["extras"] = extras.DeepClone();
        if (today is not null)
            fields["today"] = today;
        if (interior is not null)
            fields["interior"] = interior.DeepClone();
        // with a silence limit (UI polish change 15): the worker is asked for its progress lines, and it is stopped only
        // when none comes for that long (a large model's check is long, not stuck); else one limit for the whole answer
        var answer = silence is { } quiet
            ? await ExchangeAsync("check_site", fields, quiet, cancel, silence: true, step: step, total: total).ConfigureAwait(false)
            : await ExchangeAsync("check_site", fields, _options.RequestTimeout, cancel).ConfigureAwait(false);
        return Guard(() => CheckResult.Parse(answer));
    }

    /// <summary>The older <c>options {jurisdiction}</c> (answered exactly as before protocol 1, with no <c>about</c>):
    /// the place's districts that have a rulebook, the city's use words and their names, and each district's uses, read
    /// from the rulebooks themselves (design_checker check.options). The Revit add-in's Setup form offers these as its
    /// Zone and Use choices (docs/decisions/2026-11-22_setup_form.md); a typed method, so its answer is read strictly:
    /// anything else in it, or a field of the wrong kind, stops the worker, as for every answer.</summary>
    public async Task<PlaceOptions> OptionsAsync(string jurisdiction, CancellationToken cancel = default)
    {
        ArgumentNullException.ThrowIfNull(jurisdiction);
        var result = await ExchangeAsync("options", new JsonObject { ["jurisdiction"] = jurisdiction }, _options.RequestTimeout,
                                         cancel, legacy: true).ConfigureAwait(false);
        return Guard(() => PlaceOptions.Parse(result.Result));
    }

    /// <summary><c>start_site {site, facts, floor_to_floor?, design_buffer?, larger_side?}</c>: the largest legal
    /// starting building on the description's lot. A null argument is not sent (the worker's default).</summary>
    public Task<WorkerAnswer> StartSiteAsync(JsonNode site, JsonNode facts, double? floorToFloor = null,
                                             double? designBuffer = null, string? largerSide = null,
                                             CancellationToken cancel = default)
    {
        ArgumentNullException.ThrowIfNull(site);
        ArgumentNullException.ThrowIfNull(facts);
        var fields = new JsonObject { ["site"] = site.DeepClone(), ["facts"] = facts.DeepClone() };
        if (floorToFloor is double f)
            fields["floor_to_floor"] = f;
        if (designBuffer is double b)
            fields["design_buffer"] = b;
        if (largerSide is not null)
            fields["larger_side"] = largerSide;
        return ExchangeAsync("start_site", fields, _options.StartSiteTimeout, cancel);
    }

    /// <summary><c>read_model {model, facts, inventory_complete?}</c>: a .3dm file read as a site description.</summary>
    public Task<WorkerAnswer> ReadModelAsync(string model, JsonNode facts, bool? inventoryComplete = null,
                                             CancellationToken cancel = default)
    {
        ArgumentNullException.ThrowIfNull(model);
        ArgumentNullException.ThrowIfNull(facts);
        var fields = new JsonObject { ["model"] = model, ["facts"] = facts.DeepClone() };
        if (inventoryComplete is bool i)
            fields["inventory_complete"] = i;
        return ExchangeAsync("read_model", fields, _options.RequestTimeout, cancel);
    }

    /// <summary>A session command (<see cref="Protocol.SessionCommands"/>): the fields it reads, and optionally the
    /// answers wanted. Read each answer with <see cref="SessionAnswer.Get"/>.</summary>
    public async Task<SessionAnswer> SessionAsync(string command, JsonObject fields, IReadOnlyList<string>? want = null,
                                                  CancellationToken cancel = default)
    {
        ArgumentNullException.ThrowIfNull(command);
        ArgumentNullException.ThrowIfNull(fields);
        if (!Protocol.SessionCommands.TryGetValue(command, out var parts))
            throw new ArgumentException($"{command} is not a session command", nameof(command));
        var copy = Fields(fields);
        if (want is not null)
        {
            var names = parts.SelectMany(p => p).ToHashSet();
            if (want.Count == 0 || want.Any(w => !names.Contains(w)))
                throw new ArgumentException($"want names answers of {command}: {string.Join(", ", names)}", nameof(want));
            copy["want"] = new JsonArray(want.Select(w => (JsonNode?)JsonValue.Create(w)).ToArray());
        }
        var answer = await ExchangeAsync(command, copy, _options.RequestTimeout, cancel, checkedFields: true).ConfigureAwait(false);
        return Guard(() => SessionAnswer.Parse(command, answer, want));
    }

    /// <summary><c>objects.left_out</c> (protocol 1.1): which of the objects the add-in saw that could be a building
    /// and aren't measured are left out of the check (<c>left_out</c>), may be part of the house (<c>touching</c>,
    /// null when an object has no box: it counts as touching) and have no box that covers all of them
    /// (<c>no_box</c>), each one entry per object, in the order sent. What each object, definition, the lot and a
    /// building's box are: host_core/left_out.py. Lengths in the model's units, <paramref name="feetPerUnit"/>
    /// feet each (Revit's internal units are feet: 1).</summary>
    /// <param name="lot">The lot's <c>{ring, box}</c>, or null when there is none (nothing is left out).</param>
    /// <param name="objects">What the add-in saw of each object: <c>{id, box, points, definition?}</c>. Send
    /// <c>definition</c> only for a family instance or linked model, never null for anything else: null means one
    /// whose definition is missing, so no box (left out and touching).</param>
    /// <param name="buildings">The measured buildings' boxes.</param>
    /// <param name="definitions">What each placed family or linked model holds, once each, or null for none.</param>
    /// <param name="feetPerUnit">How many feet one model unit is.</param>
    /// <param name="cancel">Cancels the wait; the worker is then stopped.</param>
    public Task<SessionAnswer> LeftOutAsync(JsonNode? lot, JsonArray objects, JsonArray buildings,
                                            JsonObject? definitions = null, double feetPerUnit = 1.0,
                                            CancellationToken cancel = default)
    {
        ArgumentNullException.ThrowIfNull(objects);
        ArgumentNullException.ThrowIfNull(buildings);
        var fields = new JsonObject
        {
            ["lot"] = lot?.DeepClone(), ["objects"] = objects.DeepClone(), ["buildings"] = buildings.DeepClone(),
            ["definitions"] = definitions?.DeepClone() ?? new JsonObject(), ["feet_per_unit"] = feetPerUnit,
        };
        return SessionAsync("objects.left_out", fields, cancel: cancel);
    }

    /// <summary>A protocol-1 command this client has no typed method for (one a later 1.x worker adds), by name, with
    /// its fields (<c>id</c>, <c>cmd</c> and <c>protocol</c> are added). Its result comes back unread: only the
    /// answer's envelope is checked (this request's id, <c>ok</c>, <c>about</c>). A command with a typed method is
    /// refused here, so its answer is always read strictly (a check's rows, a session command's refused parts); so
    /// are the older commands (check, start, facts, options, sample_site), whose answers carry no <c>about</c>.</summary>
    public Task<WorkerAnswer> SendAsync(string command, JsonObject? fields = null, TimeSpan? timeout = null,
                                        CancellationToken cancel = default)
    {
        ArgumentNullException.ThrowIfNull(command);
        if (Protocol.Legacy.Contains(command))
            throw new ArgumentException($"{command} is an older command, not part of protocol 1; use check_site or start_site", nameof(command));
        if (Protocol.ModelCommands.Contains(command) || Protocol.SessionCommands.ContainsKey(command))
            throw new ArgumentException($"{command} has its own method (HelloAsync, ReadModelAsync, CheckSiteAsync, " +
                                        "StartSiteAsync or SessionAsync), which reads its answer strictly", nameof(command));
        return ExchangeAsync(command, fields ?? new JsonObject(), timeout ?? _options.RequestTimeout, cancel);
    }

    // ---- one request, one answer ----------------------------------------------------------------------------------

    private static JsonObject Fields(JsonObject fields)
    {
        foreach (var name in Protocol.Envelope)
            if (fields.ContainsKey(name))
                throw new ArgumentException($"\"{name}\" is the request's own field, never a command's", nameof(fields));
        return (JsonObject)fields.DeepClone();
    }

    private async Task<WorkerAnswer> ExchangeAsync(string command, JsonObject fields, TimeSpan timeout,
                                                   CancellationToken cancel, bool checkedFields = false, bool legacy = false,
                                                   bool silence = false, IProgress<string>? step = null, TimeSpan? total = null)
    {
        var body = checkedFields ? fields : Fields(fields);
        await _one.WaitAsync(cancel).ConfigureAwait(false);
        try
        {
            if (_stopped is not null)
                throw new WorkerStoppedException($"The Gordium checker was stopped ({_stopped}); start it again");
            var id = ++_nextId;
            // an older command names no protocol (it is answered as before protocol 1, without about)
            var request = legacy ? new JsonObject { ["id"] = id, ["cmd"] = command }
                                 : new JsonObject { ["id"] = id, ["cmd"] = command, ["protocol"] = Protocol.Version };
            if (silence)
                request["progress"] = true;              // the worker writes a line as each stage starts, and while it works
            foreach (var (k, v) in body.ToList())
            {
                body.Remove(k);
                request[k] = v;
            }
            string line;
            try
            {
                line = request.ToJsonString();         // never indented: one line; a NaN or infinity throws here
            }
            catch (ArgumentException e)
            {
                throw new ArgumentException($"{command}: a value JSON can't carry: {e.Message}", nameof(fields), e);
            }
            // one time limit for the whole request: sending it, then its answer
            var clock = Stopwatch.StartNew();
            await WriteAsync(line, command, timeout, timeout, cancel).ConfigureAwait(false);
            if (silence)
            {
                // each progress line of this request starts the silence again; the first other line is the answer
                while (true)
                {
                    // the next line within the silence, and within what is left of the ceiling
                    var toCap = total is { } cap ? cap - clock.Elapsed : TimeSpan.MaxValue;
                    if (toCap <= TimeSpan.Zero || toCap < timeout)
                    {
                        var said0 = await ReadAsync(command, toCap > TimeSpan.Zero ? toCap : TimeSpan.Zero, total!.Value, cancel).ConfigureAwait(false);
                        if (Protocol.StepOf(said0, id) is not { } stage0)
                            return Answer(command, id, said0, legacy);
                        step?.Report(stage0);
                        continue;
                    }
                    var said = await ReadAsync(command, timeout, timeout, cancel, silence: true).ConfigureAwait(false);
                    if (Protocol.StepOf(said, id) is not { } stage)
                        return Answer(command, id, said, legacy);
                    step?.Report(stage);
                }
            }
            var left = timeout - clock.Elapsed;
            var text = await ReadAsync(command, left > TimeSpan.Zero ? left : TimeSpan.Zero, timeout, cancel).ConfigureAwait(false);
            return Answer(command, id, text, legacy);
        }
        finally
        {
            _one.Release();
        }
    }

    private async Task WriteAsync(string line, string command, TimeSpan timeout, TimeSpan limit, CancellationToken cancel)
    {
        var bytes = Utf8.GetBytes(line + "\n");          // UTF-8, no byte-order mark: the worker refuses one
        try
        {
            // a worker that stops reading its input would block the write when the pipe is full: never wait forever
            await Write(_process.StandardInput.BaseStream, bytes).WaitAsync(timeout, cancel).ConfigureAwait(false);
        }
        catch (TimeoutException)
        {
            Stop($"{command} couldn't be sent in {limit.TotalSeconds:0} s");
            throw new WorkerTimeoutException(
                $"The Gordium checker didn't take {command} in {limit.TotalSeconds:0} s, so it was stopped and nothing from it is shown")
            { Limit = limit, Command = command };
        }
        catch (OperationCanceledException) when (cancel.IsCancellationRequested)
        {
            Stop($"{command} was cancelled");
            throw;
        }
        catch (Exception e) when (e is IOException or ObjectDisposedException or InvalidOperationException)
        {
            throw Exited($"The Gordium checker stopped before {command} could be sent");
        }
    }

    private static async Task Write(Stream stdin, byte[] bytes)
    {
        await stdin.WriteAsync(bytes).ConfigureAwait(false);
        await stdin.FlushAsync().ConfigureAwait(false);
    }

    private async Task<string> ReadAsync(string command, TimeSpan timeout, TimeSpan limit, CancellationToken cancel, bool silence = false)
    {
        using var wait = CancellationTokenSource.CreateLinkedTokenSource(cancel);
        wait.CancelAfter(timeout);
        try
        {
            return await _lines.Reader.ReadAsync(wait.Token).ConfigureAwait(false);
        }
        catch (ChannelClosedException)
        {
            if (_readFailure is not null)
                throw Untrusted($"{command}: the Gordium checker wrote a line that isn't UTF-8", _readFailure);
            throw Exited($"The Gordium checker stopped before answering {command}");
        }
        catch (OperationCanceledException) when (cancel.IsCancellationRequested)
        {
            Stop($"{command} was cancelled");
            throw;
        }
        catch (OperationCanceledException) when (silence)
        {
            Stop($"no word from the checker on {command} for {limit.TotalSeconds:0} s");
            throw new WorkerTimeoutException(
                $"The Gordium checker said nothing for {limit.TotalSeconds:0} s while answering {command}, so it was stopped and nothing from it is shown")
            { Limit = limit, Silent = true, Command = command };
        }
        catch (OperationCanceledException)
        {
            Stop($"no answer to {command} in {limit.TotalSeconds:0} s");
            throw new WorkerTimeoutException(
                $"The Gordium checker gave no answer to {command} in {limit.TotalSeconds:0} s, so it was stopped and nothing from it is shown")
            { Limit = limit, Command = command };
        }
    }

    private WorkerAnswer Answer(string command, long id, string text, bool legacy = false)
    {
        JsonElement answer;
        try
        {
            answer = StrictJson.Parse(text);
        }
        catch (JsonException e)
        {
            throw Untrusted($"{command}: the Gordium checker's answer isn't JSON ({e.Message})", e);
        }
        if (answer.ValueKind != JsonValueKind.Object)
            throw Untrusted($"{command}: the Gordium checker's answer is {StrictJson.Kind(answer)}, not an object");
        if (!answer.TryGetProperty("id", out var gotId) || gotId.ValueKind != JsonValueKind.Number
            || !gotId.TryGetInt64(out var got) || got != id)
        {
            var words = answer.TryGetProperty("error", out var err) && err.ValueKind == JsonValueKind.String
                ? $" (it said: {err.GetString()})" : "";
            throw Untrusted($"{command}: the Gordium checker's answer isn't to this request (id {id}){words}, " +
                            "so it was stopped and nothing from it is shown");
        }
        if (!answer.TryGetProperty("ok", out var ok) || ok.ValueKind is not (JsonValueKind.True or JsonValueKind.False))
            throw Untrusted($"{command}: the Gordium checker's answer has no \"ok\" true or false");
        if (ok.ValueKind == JsonValueKind.False)
        {
            if (!answer.TryGetProperty("error", out var error) || error.ValueKind != JsonValueKind.String)
                throw Untrusted($"{command}: the Gordium checker refused without saying why (no \"error\" words)");
            string? trace = answer.TryGetProperty("trace", out var t) && t.ValueKind == JsonValueKind.String ? t.GetString() : null;
            throw new WorkerRefusedException(command, error.GetString()!, trace);
        }
        return Guard(() =>
        {
            var result = StrictJson.Object(answer, "result", "the answer");
            // an older command's answer has no about: this client's own hello's stands for it
            var about = legacy ? About : WorkerAbout.Parse(StrictJson.Object(answer, "about", "the answer"), "about");
            return new WorkerAnswer(result, about);
        });
    }

    /// <summary>Reads an answer; anything wrong with it stops the worker before it is thrown.</summary>
    private T Guard<T>(Func<T> read)
    {
        try
        {
            return read();
        }
        catch (WorkerProtocolException e)
        {
            Stop(e.Message);
            throw;
        }
    }

    private WorkerProtocolException Untrusted(string message, Exception? inner = null)
    {
        Stop(message);
        return new WorkerProtocolException(message, inner);
    }

    private WorkerExitedException Exited(string message)
    {
        int? code = null;
        try
        {
            if (_process.WaitForExit(2000))
                code = _process.ExitCode;
        }
        catch (InvalidOperationException) { }
        Stop(message);
        string tail;
        lock (_log)
            tail = string.Join("\n", _log);
        return new WorkerExitedException(message, code, tail);
    }

    private void Stop(string why)
    {
        _stopped ??= why;
        try
        {
            if (!_process.HasExited)
                _process.Kill(entireProcessTree: true);
        }
        catch (Exception e) when (e is InvalidOperationException or System.ComponentModel.Win32Exception or NotSupportedException) { }
    }

    /// <summary>Stops the worker: closes its input (it ends on its own), then kills it if it hasn't within 2 s.</summary>
    public void Dispose()
    {
        if (_stopped is null)
        {
            _stopped = "it was closed";
            try
            {
                _process.StandardInput.Close();
                if (!_process.WaitForExit(2000))
                    _process.Kill(entireProcessTree: true);
            }
            catch (Exception e) when (e is IOException or InvalidOperationException or System.ComponentModel.Win32Exception) { }
        }
        else
        {
            Stop(_stopped);
        }
        _process.Dispose();
    }
}
