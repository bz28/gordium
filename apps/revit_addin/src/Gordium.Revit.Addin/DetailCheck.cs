using System.IO;
using Autodesk.Revit.DB;
using Gordium.Revit.Reading;

namespace Gordium.Revit.Addin;

/// <summary>The trial's check of the detail-level reading (reading design note, section 8, "Detail level"), asked for
/// by request file (detail_check_request.json, any content) while Revit is idle: a Generic Model family holding a
/// 4 × 4 × 4 ft box shown at every level and, beside it, a 2 × 2 × 2 ft box shown at Coarse only; placed in a new
/// model, read by RevitRead, and logged: what the Fine geometry holds, what the coarser geometry holds, and the box
/// the reader gives the family (a left-out object) with and without the coarser part. Expected: Fine one solid, the
/// coarser geometry the Coarse-only box too, and the reader's box reaching past the Fine one.</summary>
internal static class DetailCheck
{
    internal static string RequestPath => Path.Combine(Path.GetDirectoryName(Trial.LogPath())!, "detail_check_request.json");

    internal static void Run(Autodesk.Revit.ApplicationServices.Application app)
    {
        var log = new Dictionary<string, object?>();
        var family = Path.Combine(Path.GetTempPath(), $"gordium_detail_{Guid.NewGuid():N}.rfa");
        var fam = app.NewFamilyDocument(SceneDraw.GenericModelTemplate(app));
        try
        {
            using (var t = new Transaction(fam, "Gordium: a family drawn per detail level"))
            {
                t.Start();
                Box(fam, 0, 0, 4, null);
                Box(fam, 10, 0, 2, new FamilyElementVisibility(FamilyElementVisibilityType.Model)
                {
                    IsShownInCoarse = true, IsShownInMedium = false, IsShownInFine = false,
                });
                t.Commit();
            }
            fam.SaveAs(family);
        }
        finally
        {
            fam.Close(false);
        }
        var doc = app.NewProjectDocument(UnitSystem.Imperial);
        try
        {
            string id;
            using (var t = new Transaction(doc, "Gordium: place it"))
            {
                t.Start();
                doc.LoadFamily(family, out var loaded);
                var symbol = (FamilySymbol)doc.GetElement(loaded.GetFamilySymbolIds().First());
                symbol.Activate();
                id = doc.Create.NewFamilyInstance(XYZ.Zero, symbol, Autodesk.Revit.DB.Structure.StructuralType.NonStructural).UniqueId;
                t.Commit();
            }
            var e = RevitRead.Model(doc, app.VersionNumber, app.VertexTolerance).Elements.Single(x => x.UniqueId == id);
            log["fine"] = Describe(e.Geometry);
            log["coarser"] = Describe(e.CoarserGeometry);
            log["box_fine"] = Box(e with { CoarserGeometry = null });
            log["box_read"] = Box(e);
        }
        finally
        {
            doc.Close(false);
            File.Delete(family);
        }
        Trial.Log("detail_check", log);
    }

    private static void Box(Document fam, double x, double y, double size, FamilyElementVisibility? visibility)
    {
        var loop = new CurveArray();
        XYZ[] c = [new(x, y, 0), new(x + size, y, 0), new(x + size, y + size, 0), new(x, y + size, 0)];
        for (var i = 0; i < 4; i++)
            loop.Append(Line.CreateBound(c[i], c[(i + 1) % 4]));
        var profile = new CurveArrArray();
        profile.Append(loop);
        var plane = SketchPlane.Create(fam, Plane.CreateByNormalAndOrigin(XYZ.BasisZ, XYZ.Zero));
        var extrusion = fam.FamilyCreate.NewExtrusion(true, profile, plane, size);
        if (visibility is not null)
            extrusion.SetVisibility(visibility);
    }

    private static string Describe(IReadOnlyList<GeometryItem>? items) => items is null ? "none"
        : string.Join(", ", items.Select(i => i switch
        {
            SolidItem s => $"solid of {s.Faces.Count} faces",
            InstanceItem { Items: { } inner } => $"instance [{Describe(inner)}]",
            InstanceItem => "instance with nothing",
            _ => i.GetType().Name,
        }));

    /// <summary>The box the reader's footprint gives the element once its coarser geometry is folded in.</summary>
    private static string Box(RevitElement e)
    {
        var folded = SiteReader.Coarser(e);
        var xs = new List<double>();
        var ys = new List<double>();
        void Walk(IReadOnlyList<GeometryItem>? items)
        {
            foreach (var i in items ?? [])
                switch (i)
                {
                    case SolidItem s:
                        foreach (var f in s.Faces)
                            foreach (var loop in f.Loops)
                                foreach (var edge in loop)
                                {
                                    xs.Add(edge.Start.X);
                                    ys.Add(edge.Start.Y);
                                }
                        break;
                    case InstanceItem { Items: { } inner }:
                        Walk(inner);
                        break;
                }
        }
        Walk(folded.Geometry);
        return xs.Count == 0 ? "none" : $"x {xs.Min():0.##} to {xs.Max():0.##}, y {ys.Min():0.##} to {ys.Max():0.##}";
    }
}
