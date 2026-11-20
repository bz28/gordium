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
    private static readonly BuiltInCategory[] Marked = [BuiltInCategory.OST_Rooms, BuiltInCategory.OST_Windows, BuiltInCategory.OST_Doors];

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
    };

    private static MarkedElement Element(Document doc, Element e)
    {
        var type = doc.GetElement(e.GetTypeId());
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
        };
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
                : dataType == SpecTypeId.Length ? MarkValueKind.Length : null;
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
            using var t = new Transaction(doc, "Gordium: add the egress marks");
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

/// <summary>"Mark for egress": adds Gordium's marks to the project if they aren't there (design note, section 3:
/// on first use), then shows the marking list, anything unset first. A minimal first view (a dialog and the log);
/// the dockable list is the later UI pass.</summary>
[Transaction(TransactionMode.Manual)]
public sealed class MarkForEgressCommand : IExternalCommand
{
    public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
    {
        var doc = commandData.Application.ActiveUIDocument?.Document;
        if (doc is null || doc.IsFamilyDocument)
        {
            TaskDialog.Show("Gordium: mark for egress", "Open a project (not a family) to mark it for egress.");
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
            var list = MarkingList.Build(RevitInterior.Model(doc), plan);
            log["headline"] = list.Headline;
            log["has_none_conflicts"] = list.HasNoneConflicts;
            log["has_none"] = list.HasNoneLines;
            log["setup_problems"] = list.SetupProblems;
            log["room_blockers"] = list.RoomBlockers;
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
            var head = added.Count == 0 ? "" : $"Added {added.Count} Gordium marks to this project.\n\n";
            var dialog = new TaskDialog("Gordium: mark for egress")
            {
                MainInstruction = list.Headline,
                MainContent = head + MarkingList.Text(list, maxRows: 25) + $"\n\nLogged to {Trial.LogPath()}",
            };
            dialog.Show();
            return Result.Succeeded;
        }
        catch (Exception e)
        {
            log["error"] = $"{e.GetType().Name}: {e.Message}";
            Trial.Log("mark_for_egress", log);
            TaskDialog.Show("Gordium: mark for egress", $"Failed: {e.GetType().Name}\n{e.Message}");
            message = e.Message;
            return Result.Failed;
        }
    }
}
