using System.Globalization;
using System.IO;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Architecture;
using Autodesk.Revit.UI;
using Gordium.Revit.Reading;
using TaskDialog = Autodesk.Revit.UI.TaskDialog;

namespace Gordium.Revit.Addin;

/// <summary>
/// The Revit layer of the architect's marks (docs/revit/revit_interior_reading_design.md, section 3): it copies the
/// project's parameter bindings and each room's, window's and door's marks into the reader's records
/// (Gordium.Revit.Reading/Records.cs), and does the steps <see cref="MarkSetup"/> decided. It decides nothing:
/// what a mark means, what to add and what the marking list shows are Gordium.Revit.Reading's, tested on the Mac.
/// </summary>
internal static class RevitMarks
{
    // levels for their "no rooms on this level" mark (a roof level's enclosed areas aren't rooms nobody drew)
    private static readonly BuiltInCategory[] Marked =
        [BuiltInCategory.OST_Rooms, BuiltInCategory.OST_Windows, BuiltInCategory.OST_Doors, BuiltInCategory.OST_Levels];

    /// <summary>The model's phases, design options and marked elements, with the project's bindings: what the
    /// marking list and (later) the interior reader need.</summary>
    internal static RevitModel Model(Document doc) => new()
    {
        Document = doc.Title,
        Phases = doc.Phases.Cast<Phase>().Select(p => Id(p.Id)!).ToList(),
        OptionSets = new FilteredElementCollector(doc).OfClass(typeof(DesignOption)).Cast<DesignOption>()
            .GroupBy(o => o.get_Parameter(BuiltInParameter.OPTION_SET_ID)?.AsElementId() ?? ElementId.InvalidElementId)
            .Select(g => new OptionSet(Id(g.Key) ?? "", doc.GetElement(g.Key)?.Name ?? "",
                                       g.Select(o => new DesignOptionRecord(Id(o.Id)!, o.Name, o.IsPrimary)).ToList()))
            .ToList(),
        ActiveOption = Id(DesignOption.GetActiveDesignOptionId(doc)),
        Marked = Marked.SelectMany(c => new FilteredElementCollector(doc).OfCategory(c).WhereElementIsNotElementType())
            .Select(e => Element(doc, e)).ToList(),
        Bindings = Bindings(doc),
        ProjectMarks = doc.ProjectInformation is { } info ? Values(info) : new Dictionary<Guid, MarkValue>(),
        VertexTolerance = doc.Application.VertexTolerance,
        Elements = RevitRead.HouseOutline(doc),          // the site slabs' rows (SiteSlabs), no geometry
    };

    private static MarkedElement Element(Document doc, Element e)
    {
        var type = doc.GetElement(e.GetTypeId());
        var size = e is FamilyInstance ? RevitInterior.TypeSize(type) : default((double? Width, double? Height));
        return new MarkedElement
        {
            UniqueId = e.UniqueId,
            BuiltInCategory = e.Category?.BuiltInCategory.ToString() ?? "",
            Name = e is Room ? e.get_Parameter(BuiltInParameter.ROOM_NAME)?.AsString() : e.Name,
            Number = e is Room r ? r.Number : e.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)?.AsString(),
            Family = (e as FamilyInstance)?.Symbol?.FamilyName,
            TypeUniqueId = type?.UniqueId,
            PhaseCreated = Id(e is Room ? e.get_Parameter(BuiltInParameter.ROOM_PHASE)?.AsElementId() : e.CreatedPhaseId),
            PhaseDemolished = Id(e.DemolishedPhaseId),
            Placement = e is Room room ? Placement(room) : null,
            DesignOption = Id(e.DesignOption?.Id),
            Instance = Values(e),
            Type = type is null ? new Dictionary<Guid, MarkValue>() : Values(type),
            TypeManufacturer = type?.get_Parameter(BuiltInParameter.ALL_MODEL_MANUFACTURER)?.AsString(),
            TypeModel = type?.get_Parameter(BuiltInParameter.ALL_MODEL_MODEL)?.AsString(),
            TypeWidth = size.Width,
            TypeHeight = size.Height,
            TypeShared = type is null ? new Dictionary<Guid, MarkValue>() : Shared(type),
        };
    }

    /// <summary>The makers' shared type parameters the clear-opening data names, by GUID only (a firm's parameter of the
    /// same name is never read as the maker's), as Revit gives them (an Area in sq ft).</summary>
    private static Dictionary<Guid, MarkValue> Shared(Element type)
    {
        var values = new Dictionary<Guid, MarkValue>();
        foreach (var g in MakerClearOpenings.SharedParameters)
            if (type.get_Parameter(g) is { } p)
                values[g] = new MarkValue(p.HasValue, null,
                                          p.StorageType == StorageType.String ? p.AsString() : null,
                                          p.StorageType == StorageType.Double ? p.AsDouble() : null);
        return values;
    }

    /// <summary><see cref="Prefill"/>, never throwing: a type that can't be written, or a transaction Revit rolled back,
    /// counts nothing as filled and gives the reason (logged as <c>clear_fill_failed</c>, and shown by the dialog and
    /// the marking list), so it never stops the marking list or the check.</summary>
    internal static (List<ClearPrefill> Filled, string? Failed) TryPrefill(Document doc, RevitModel model, Dictionary<string, object?> log)
    {
        (List<ClearPrefill> Filled, string? Failed) result;
        try
        {
            result = Prefill(doc, model);
        }
        catch (Exception e) when (e is InvalidOperationException or Autodesk.Revit.Exceptions.ApplicationException)
        {
            result = ([], $"{e.Message}; nothing was written");
        }
        log["clear_filled"] = result.Filled.Select(p => $"{p.TypeId} {p.Label}: {p.Source}").ToList();
        if (result.Failed is not null)
            log["clear_fill_failed"] = result.Failed;
        return result;
    }

    /// <summary>Writes each window type's draft clear opening (<see cref="ClearPrefills"/>: only types whose three
    /// marks are empty, in one transaction; never <c>Gordium: Clear confirmed</c>). A mark Revit won't set throws, and
    /// the transaction rolls back: nothing is filled half way. Returns the plans written, and why none were when Revit
    /// rolled the transaction back.</summary>
    internal static (List<ClearPrefill> Filled, string? Failed) Prefill(Document doc, RevitModel model)
    {
        var todo = ClearPrefills.Plan(model).Where(p => p.State == PrefillState.Fill).ToList();
        if (todo.Count == 0)
            return (todo, null);
        using var t = new Transaction(doc, "Gordium: fill the makers' clear openings (drafts to confirm)");
        t.Start();
        foreach (var p in todo)
        {
            var type = doc.GetElement(p.TypeId) ?? throw new InvalidOperationException($"no type {p.TypeId}");
            void Set(MarkDefinition m, Func<Parameter, bool> set)
            {
                var param = type.get_Parameter(m.Guid);
                // re-checked here: a mark set since the plan was read is never written over
                var taken = param is not null && (param.StorageType == StorageType.String
                    ? !string.IsNullOrWhiteSpace(param.AsString()) : param.HasValue);
                if (param is null || param.IsReadOnly || taken || !set(param))
                    throw new InvalidOperationException($"{m.Name} on {p.Label} couldn't be filled");
            }
            Set(Marks.ClearWidth, q => q.Set(p.ClearWidth!.Value));
            Set(Marks.ClearHeight, q => q.Set(p.ClearHeight!.Value));
            Set(Marks.ClearSource, q => q.Set(p.Source!));
        }
        // Revit rolls a transaction back (a failure it can't resolve, an element another user owns) by returning a
        // status, not by throwing: only a commit Revit reports done counts as filled
        var (filled, failed) = ClearPrefills.Outcome(todo, t.Commit().ToString());
        return (filled.ToList(), failed);
    }

    /// <summary>Writes <paramref name="writes"/> in ONE transaction named <paramref name="name"/> (one Ctrl+Z takes it
    /// all back): each on its element (or type; <see cref="SetupFacts.ProjectInformation"/> is Project Information), as
    /// Revit stores its kind. The one writer of the request files' marks (SetMarks) and the Setup form's Save and
    /// accepts. A write Revit refuses (no such parameter, read-only, Set false) is listed refused, never counted as
    /// written; with every write refused nothing is committed. Returns what was written, what was refused, and how the
    /// transaction ended (only "Committed" means the model holds them).</summary>
    internal static (List<string> Applied, List<string> Refused, string Status) Write(Document doc, string name, IReadOnlyList<MarkWrite> writes)
    {
        var applied = new List<string>();
        var refused = new List<string>();
        if (writes.Count == 0)
            return (applied, refused, "Nothing");
        using var t = new Transaction(doc, name);
        t.Start();
        foreach (var w in writes)
        {
            var e = w.Element == SetupFacts.ProjectInformation ? doc.ProjectInformation : doc.GetElement(w.Element);
            var p = e?.get_Parameter(w.Mark.Guid);
            var done = p is { IsReadOnly: false } && (w.Mark.Kind switch
            {
                MarkValueKind.YesNo or MarkValueKind.Integer => p.Set(w.Value.Integer!.Value),
                MarkValueKind.Length => p.Set(w.Value.Number!.Value),
                _ => p.Set(w.Value.Text!),
            });
            (done ? applied : refused).Add($"{w.Label}: {w.Mark.Name} = {w.Value.Text ?? w.Value.Integer?.ToString(CultureInfo.InvariantCulture) ?? w.Value.Number?.ToString(CultureInfo.InvariantCulture)}" +
                                           (done ? "" : p is null ? " (the element has no such parameter)" : " (Revit refused it)"));
        }
        if (applied.Count == 0)
        {
            t.RollBack();
            return (applied, refused, "RolledBack");
        }
        return (applied, refused, t.Commit().ToString());
    }

    /// <summary>Each window's and door's rooms on its two sides in the last phase (<c>FromRoom</c>, <c>ToRoom</c>) and
    /// its level: what the Setup checklist's escape-opening and exit-door suggestions are based on (never sent).</summary>
    internal static List<OpeningSides> Sides(Document doc)
    {
        var last = doc.Phases.Cast<Phase>().LastOrDefault();
        var sides = new List<OpeningSides>();
        foreach (var c in new[] { BuiltInCategory.OST_Windows, BuiltInCategory.OST_Doors })
            foreach (var fi in new FilteredElementCollector(doc).OfCategory(c).WhereElementIsNotElementType().OfType<FamilyInstance>())
            {
                Room? from = null, to = null;
                if (last is not null)
                {
                    try
                    {
                        from = fi.get_FromRoom(last);
                        to = fi.get_ToRoom(last);
                    }
                    catch (Autodesk.Revit.Exceptions.ApplicationException) { }     // no rooms read: no suggestion for it
                }
                var level = doc.GetElement(fi.LevelId) as Level;
                sides.Add(new OpeningSides(fi.UniqueId, from?.UniqueId, to?.UniqueId, level?.UniqueId, level?.Name, level?.ProjectElevation));
            }
        return sides;
    }

    /// <summary>Revit's own three states of a room that isn't on the plan: no <c>Location</c> (unplaced); placed
    /// with no area and no boundary loop (not enclosed); placed with a boundary but no area (redundant: another room
    /// holds the area). To check on real models.</summary>
    private static RoomPlacement Placement(Room room)
    {
        if (room.Location is null)
            return RoomPlacement.Unplaced;
        if (room.Area > 0)
            return RoomPlacement.Placed;
        var loops = room.GetBoundarySegments(new SpatialElementBoundaryOptions());
        return loops is null || loops.Count == 0 ? RoomPlacement.NotEnclosed : RoomPlacement.Redundant;
    }

    /// <summary>Every Gordium mark the element has, by GUID (never by name), as Revit gives it.</summary>
    internal static Dictionary<Guid, MarkValue> Values(Element e)
    {
        var values = new Dictionary<Guid, MarkValue>();
        foreach (var m in Marks.All)
        {
            if (e.get_Parameter(m.Guid) is not { } p)
                continue;
            values[m.Guid] = new MarkValue(
                p.HasValue,
                p.StorageType == StorageType.Integer ? p.AsInteger() : null,
                p.StorageType == StorageType.String ? p.AsString() : null,
                p.StorageType == StorageType.Double ? p.AsDouble() : null);
        }
        return values;
    }

    /// <summary>Every parameter bound in the project (<c>Document.ParameterBindings</c>).</summary>
    internal static List<BoundParameter> Bindings(Document doc)
    {
        var bound = new List<BoundParameter>();
        var it = doc.ParameterBindings.ForwardIterator();
        while (it.MoveNext())
        {
            if (it.Key is not { } def || it.Current is not ElementBinding binding)
                continue;
            Guid? guid = def is InternalDefinition internalDef && doc.GetElement(internalDef.Id) is SharedParameterElement shared
                ? shared.GuidValue : null;
            var dataType = def.GetDataType();
            MarkValueKind? kind = dataType == SpecTypeId.Boolean.YesNo ? MarkValueKind.YesNo
                : dataType == SpecTypeId.String.Text ? MarkValueKind.Text
                : dataType == SpecTypeId.Length ? MarkValueKind.Length
                : dataType == SpecTypeId.Int.Integer ? MarkValueKind.Integer : null;
            bound.Add(new BoundParameter(def.Name, guid, kind, dataType.TypeId, binding is InstanceBinding,
                                         binding.Categories.Cast<Category>().Select(c => c.BuiltInCategory.ToString()).ToList()));
        }
        return bound;
    }

    private static ForgeTypeId Spec(MarkValueKind kind) => kind switch
    {
        MarkValueKind.YesNo => SpecTypeId.Boolean.YesNo,
        MarkValueKind.Text => SpecTypeId.String.Text,
        MarkValueKind.Length => SpecTypeId.Length,
        MarkValueKind.Integer => SpecTypeId.Int.Integer,
        _ => throw new ArgumentOutOfRangeException(nameof(kind)),
    };

    /// <summary>Does the steps that add or extend a mark, in one transaction, through a shared-parameter file of
    /// Gordium's own made for the purpose (the architect's own shared-parameter file is put back after, untouched).
    /// Returns the steps done.</summary>
    internal static List<MarkSetupStep> AddMarks(Document doc, Autodesk.Revit.ApplicationServices.Application app,
                                                 IReadOnlyList<MarkSetupStep> plan)
    {
        var todo = plan.Where(s => s.Action is MarkSetupAction.Add or MarkSetupAction.AddCategories).ToList();
        if (todo.Count == 0)
            return todo;
        var file = Path.Combine(Path.GetTempPath(), $"gordium_marks_{Guid.NewGuid():N}.txt");
        File.WriteAllText(file, "");
        var theirs = app.SharedParametersFilename;
        try
        {
            app.SharedParametersFilename = file;
            var definitions = app.OpenSharedParameterFile()
                ?? throw new InvalidOperationException("Revit couldn't open Gordium's shared-parameter file " + file);
            var group = definitions.Groups.get_Item(Marks.Group) ?? definitions.Groups.Create(Marks.Group);
            using var t = new Transaction(doc, ResultRows.MarksTransaction);
            t.Start();
            foreach (var s in todo)
            {
                var m = s.Mark;
                var def = group.Definitions.get_Item(m.Name) ?? group.Definitions.Create(
                    new ExternalDefinitionCreationOptions(m.Name, Spec(m.Kind))
                    {
                        GUID = m.Guid, Description = m.Description, UserModifiable = true, Visible = true,
                    });
                var categories = app.Create.NewCategorySet();
                foreach (var c in s.Categories)
                    categories.Insert(Category.GetCategory(doc, Enum.Parse<BuiltInCategory>(c))
                                      ?? throw new InvalidOperationException($"no {c} category in this project"));
                ElementBinding binding = m.Binding == MarkBinding.Instance
                    ? app.Create.NewInstanceBinding(categories) : app.Create.NewTypeBinding(categories);
                var done = s.Action == MarkSetupAction.Add
                    ? doc.ParameterBindings.Insert(def, binding, GroupTypeId.Data)
                    : doc.ParameterBindings.ReInsert(def, binding, GroupTypeId.Data);
                if (!done)
                    throw new InvalidOperationException($"Revit didn't bind {m.Name} to {string.Join(", ", s.Categories)}");
            }
            t.Commit();
            return todo;
        }
        finally
        {
            app.SharedParametersFilename = theirs;
            try { File.Delete(file); } catch (IOException) { }
        }
    }

    private static string? Id(ElementId? id) =>
        id is null || id == ElementId.InvalidElementId ? null : id.Value.ToString(CultureInfo.InvariantCulture);
}

/// <summary>"Mark facts": adds Gordium's marks to the project if they aren't there (design note, section 3: on first
/// use), fills the makers' clear openings as drafts, logs the marking list, and opens the Setup form in the Gordium
/// pane (docs/decisions/2026-11-22_setup_form.md), where the architect states the facts.</summary>
[Transaction(TransactionMode.Manual)]
public sealed class MarkForEgressCommand : IExternalCommand
{
    public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
    {
        var doc = commandData.Application.ActiveUIDocument?.Document;
        if (doc is null || doc.IsFamilyDocument)
        {
            TaskDialog.Show("Gordium: mark facts", "Open a project (not a family) to mark its facts.");
            return Result.Cancelled;
        }
        var log = new Dictionary<string, object?> { ["document"] = doc.Title };
        try
        {
            var plan = MarkSetup.Plan(RevitMarks.Bindings(doc));
            var added = RevitMarks.AddMarks(doc, commandData.Application.Application, plan);
            log["added"] = added.Select(s => $"{s.Action}: {s.Mark.Name} ({string.Join(", ", s.Categories)})").ToList();
            // the model with its inside read (as Read inside and a check read it), so the list's has-none ticks, their
            // conflicts and proposals are the reader's own
            var model = RevitInterior.Model(doc);
            // each window type a maker's formula covers, its three Clear marks empty: filled as a draft (never the
            // Clear confirmed stamp), then the model read again so the list shows what is now in it
            var (filled, failed) = RevitMarks.TryPrefill(doc, model, log);
            if (filled.Count > 0)
                model = RevitInterior.Model(doc);
            var list = MarkingList.Build(model, plan, clearWriteFailed: failed);
            log["clear_lines"] = list.ClearLines;
            // every element the list counts by type, by id
            log["stair_candidates"] = (model.Interior?.StairCandidates ?? [])
                .Select(c => $"{c.UniqueId} {c.BuiltInCategory.Replace("OST_", "")} \"{c.Name}\": {c.Kind}" +
                             (StairReader.InsideWindowOrDoor(c) ? " (inside its window or door: not a stair)" : "") +
                             (StairReader.ClearedByArchitect(c) ? $" (marked {Marks.NotAStair.Name} Yes: cleared by the architect)" : "")).ToList();
            log["unknown_area_each"] = InteriorReader.UnknownAreaWords(model);
            log["headline"] = list.Headline;
            log["has_none_conflicts"] = list.HasNoneConflicts;
            log["has_none"] = list.HasNoneLines;
            log["setup_problems"] = list.SetupProblems;
            log["room_blockers"] = list.RoomBlockers;
            log["unknown_areas"] = list.UnknownAreas;
            log["level_conflicts"] = list.LevelConflicts;
            log["stair_blockers"] = list.StairBlockers;
            log["not_a_stair_conflicts"] = list.NotAStairConflicts;
            log["not_a_stair"] = list.NotAStair;
            log["summary"] = list.Summary;
            log["rows"] = list.Rows.Select(r => new Dictionary<string, object?>
            {
                ["id"] = r.Id, ["kind"] = r.Kind.ToString(), ["label"] = r.Label, ["needs_marking"] = r.NeedsMarking,
                ["marks"] = r.Cells.ToDictionary(c => c.Mark.Name, c => (object?)new Dictionary<string, object?>
                {
                    ["state"] = c.State.ToString(), ["value"] = c.Value, ["words"] = c.Words, ["suggestion"] = c.Suggestion,
                }),
            }).ToList();
            Trial.Log("mark_for_egress", log);
            // the Setup form in the pane (design pass pieces 7 and 9, built): the facts to set, the checklist with its
            // counts and suggestions, in place of the dialog's text (the list above stays in the log)
            if (added.Count > 0 || filled.Count > 0 || failed is not null)
                ResultsPane.Say(ClearPrefills.StatusLine(added.Count, ClearPrefills.Head(filled.Count, failed)));
            SetupRun.Show(commandData.Application, doc);
            return Result.Succeeded;
        }
        catch (Exception e)
        {
            log["error"] = $"{e.GetType().Name}: {e.Message}";
            Trial.Log("mark_for_egress", log);
            TaskDialog.Show("Gordium: mark facts", $"Failed: {e.GetType().Name}\n{e.Message}");
            message = e.Message;
            return Result.Failed;
        }
    }
}
