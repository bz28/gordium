using System.Globalization;
using System.Text.Json.Nodes;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>Makers' clear-opening formulas (apps/revit_addin/data/maker_clear_openings.json; design note, section 3):
/// each entry reproduces rows of the maker's own published table, the type size is read only when it can only be the
/// frame, and the pre-fill is a draft: never over the architect's values, never the stamp, so never a clear opening
/// sent (no pass) before the architect confirms it.</summary>
public sealed class MakerClearOpeningsTests
{
    private const double In64 = 1.0 / 64;

    private static MakerFormula Marvin => MakerClearOpenings.Entries.Single(e => e.Id == "marvin_ultimate_casement");

    /// <summary>A length as Marvin's table prints it ("1-8 57/64": feet, inches and a fraction), in inches.</summary>
    internal static double FeetInches(string s)
    {
        var parts = s.Split(' ');
        var fi = parts[0].Split('-');
        double inches = int.Parse(fi[0], CultureInfo.InvariantCulture) * 12 + int.Parse(fi[1], CultureInfo.InvariantCulture);
        if (parts.Length == 2)
        {
            var f = parts[1].Split('/');
            inches += double.Parse(f[0], CultureInfo.InvariantCulture) / double.Parse(f[1], CultureInfo.InvariantCulture);
        }
        return inches;
    }

    [Fact]
    public void The_table_lengths_read_as_printed() =>
        Assert.Equal(20.890625, FeetInches("1-8 57/64"), 12);

    // ---- the data reproduces the maker's published rows -----------------------------------------------------

    [Fact]
    public void Marvin_2864_is_reproduced_from_its_frame_size_by_the_formula()
    {
        // Marvin ADM, UCA UCANF-6 (PDF page 8): "2864 1-8 57/64 (531) 4-10 1/64 (1473) 8.42 (0.78) E ..."; its frame
        // (UCA UCANF-29, Standard Unit Measurements: Casement): CN 28 "2-4", CN 64 "5-3 1/8"
        var (fill, why) = ClearPrefills.Compute(Marvin, 28.0 / 12, 63.125 / 12);
        Assert.Null(why);
        var (w, h, _) = fill!.Value;
        Assert.Equal(20.875, w * 12, 9);                          // 28 - 7 1/8
        Assert.Equal(58.0, h * 12, 9);                            // 63 1/8 - 5 1/8
        double pw = FeetInches("1-8 57/64"), ph = FeetInches("4-10 1/64");
        Assert.InRange(pw - w * 12, 0, In64 + 1e-9);              // never more than Marvin's table, within its 1/64 step
        Assert.InRange(ph - h * 12, 0, In64 + 1e-9);
        AreaBetween(8.42, w * h, pw * ph / 144);                  // the table's own area (w, h in feet: w x h sq ft)
        // the row Marvin marks E: the draft's own numbers clear R319.2's 20 in, 24 in and 5.7 sq ft (arithmetic only:
        // the E mark itself is never read, and the draft is never sent until confirmed)
        Assert.True(w * 12 >= 20 && h * 12 >= 24 && w * h >= 5.7);
    }

    public static TheoryData<string> CheckedRows()
    {
        var rows = new TheoryData<string>();
        foreach (var r in DataRoot()["entries"]!.AsArray().SelectMany(e => e!["checked_rows"]!.AsArray()))
            rows.Add(r!.ToJsonString());
        return rows;
    }

    private static JsonObject DataRoot() => JsonNode.Parse(MakerClearOpenings.Read())!.AsObject();

    [Theory]
    [MemberData(nameof(CheckedRows))]
    public void Every_checked_row_is_reproduced_within_the_tables_step_and_never_above_it(string json)
    {
        var row = JsonNode.Parse(json)!.AsObject();
        var cn = row["cn"]!.GetValue<string>();
        double fw = row["frame_width"]!.GetValue<double>(), fh = row["frame_height"]!.GetValue<double>();
        // the row's frame is the standard table's frame size for its call number (CN 2864: width 28, height 64)
        Assert.Equal(fw, Marvin.FrameWidths[Cn("width", cn[..2])]);
        Assert.Equal(fh, Marvin.FrameHeights[Cn("height", cn[2..])]);
        var p = row["published"]!;
        double pw = FeetInches(p["clear_width"]!.GetValue<string>()), ph = FeetInches(p["clear_height"]!.GetValue<string>());
        var (w, h) = Marvin.Clear(fw, fh);
        Assert.InRange(pw - w, 0, In64 + 1e-9);
        Assert.InRange(ph - h, 0, In64 + 1e-9);
        AreaBetween(p["area_ft2"]!.GetValue<double>(), w * h / 144, pw * ph / 144);
    }

    /// <summary>Marvin's printed area (to 0.01 sq ft) lies between the formula's area and the printed width times
    /// height, by Marvin's area formula ((W x H) / 144): the table works from a figure between the two (CN 2060: 4.828
    /// and 4.835, printed 4.83), so a formula or unit error (inches for feet, the narrow-frame offset) falls outside.</summary>
    private static void AreaBetween(double published, double formula, double printed)
    {
        Assert.InRange(published, Math.Min(formula, printed) - 0.005, Math.Max(formula, printed) + 0.005);
        Assert.True(formula <= published + 0.005, "the formula's area is never above Marvin's");
    }

    private static int Cn(string axis, string cn) =>
        DataRoot()["entries"]![0]!["standard_sizes"]![axis]!.AsArray().Select(x => x!["cn"]!.GetValue<string>()).ToList().IndexOf(cn);

    [Fact]
    public void Every_entry_has_a_checked_row_and_its_source()
    {
        var root = DataRoot();
        Assert.Equal(MakerClearOpenings.Format, root["format"]!.GetValue<string>());
        Assert.Equal("2026-11-20", MakerClearOpenings.Version);
        foreach (var e in root["entries"]!.AsArray())
        {
            Assert.NotEmpty(e!["checked_rows"]!.AsArray());
            var source = e["sources"]![e["formula"]!["source"]!.GetValue<string>()]!;
            foreach (var key in new[] { "url", "accessed", "sha256", "formula_page", "formula_quote", "table_page", "table_quote" })
                Assert.False(string.IsNullOrWhiteSpace(source[key]?.GetValue<string>()), key);
        }
        // the formula the code uses is the one the quote says
        Assert.Contains("Clear Opening Width = Frame OSM Width - 7 1/8\"", Marvin.FormulaQuote);
        Assert.Contains("Clear Opening Height = Frame OSM Height - 5 1/8\"", Marvin.FormulaQuote);
        Assert.Equal(7.125, Marvin.WidthMinus);
        Assert.Equal(5.125, Marvin.HeightMinus);
    }

    [Fact]
    public void A_frame_size_is_never_also_a_rough_or_masonry_size_so_a_standard_frame_is_unambiguous()
    {
        foreach (var e in MakerClearOpenings.Entries)
        {
            Assert.DoesNotContain(e.FrameWidths, w => MakerClearOpenings.Listed(w, e.RoughWidths.Concat(e.MasonryWidths)));
            Assert.DoesNotContain(e.FrameHeights, h => MakerClearOpenings.Listed(h, e.RoughHeights.Concat(e.MasonryHeights)));
        }
    }

    [Fact]
    public void A_file_of_another_format_or_missing_a_field_is_refused()
    {
        Assert.Throws<FormatException>(() => MakerClearOpenings.Parse("{\"format\": \"x\"}"));
        var root = DataRoot();
        root["entries"]![0]!["formula"]!["clear_width"]!.AsObject().Remove("frame_width_minus");
        Assert.Throws<FormatException>(() => MakerClearOpenings.Parse(root.ToJsonString()));
    }

    // ---- which types match, and which sizes are read ---------------------------------------------------------

    [Fact]
    public void A_type_matches_on_its_manufacturer_and_model_exactly_ignoring_case()
    {
        Assert.Same(Marvin, MakerClearOpenings.Match(" marvin ", "ULTIMATE CASEMENT"));
        Assert.Null(MakerClearOpenings.Match("Marvin", "Ultimate Casement Narrow Frame"));
        Assert.Null(MakerClearOpenings.Match("Marvin Inc", "Ultimate Casement"));
        Assert.Null(MakerClearOpenings.Match(null, "Ultimate Casement"));
        Assert.Null(MakerClearOpenings.Match("Marvin", null));
    }

    public static TheoryData<double?, double?, string> NoFill() => new()
    {
        { 29, 63.625, "rough opening" },            // CN 2864's rough opening: the formula needs the frame
        { 28.5, 63.375, "masonry opening" },
        { 28.25, 63.125, "aren't one of Marvin's standard frame sizes" },
        { 18, 63.125, "outside where Gordium uses the formula" },     // under 20 in: Marvin's other formula
        { 40, 63.125, "outside where Gordium uses the formula" },     // over 36 in: custodial limiters may apply
        { 28, 77.125, "outside where Gordium uses the formula" },
        { null, 63.125, "no Width and Height of its own" },
    };

    [Theory]
    [MemberData(nameof(NoFill))]
    public void A_size_that_isnt_surely_the_frame_or_is_out_of_range_is_not_filled(double? w, double? h, string why)
    {
        var (fill, words) = ClearPrefills.Compute(Marvin, w / 12, h / 12);
        Assert.Null(fill);
        Assert.Contains(why, words);
    }

    // ---- the pre-fill: a draft, never over the architect's values, never confirmed ----------------------------

    private static MarkedElement Window(string id, string? maker = "Marvin", string? model = "Ultimate Casement",
                                        double w = 28, double h = 63.125, Dictionary<Guid, MarkValue>? type = null) => new()
    {
        UniqueId = id, BuiltInCategory = Marks.Windows, Name = "CN 2864", Family = "Marvin Ultimate Casement",
        TypeUniqueId = "t-" + id, TypeManufacturer = maker, TypeModel = model, TypeWidth = w / 12, TypeHeight = h / 12,
        Type = type ?? new Dictionary<Guid, MarkValue>(),
    };

    private static RevitModel Model(params MarkedElement[] e) => new() { Document = "house.rvt", Marked = e };

    [Fact]
    public void An_empty_matching_type_is_filled_as_a_draft_naming_the_maker_page_and_formula()
    {
        var p = Assert.Single(ClearPrefills.Plan(Model(Window("a"), Window("b") with { TypeUniqueId = "t-a" })));   // once per type
        Assert.Equal(PrefillState.Fill, p.State);
        Assert.Equal(20.875 / 12, p.ClearWidth!.Value, 12);
        Assert.Equal(58.0 / 12, p.ClearHeight!.Value, 12);
        Assert.StartsWith(ClearPrefills.SourcePrefix + "Marvin Ultimate Casement (UCA), full frame, UCA UCANF-25 (PDF page 27)", p.Source);
        Assert.Contains("clear width = frame width - 7.125 in, clear height = frame height - 5.125 in; frame 28 in by 63.125 in", p.Source);
        Assert.StartsWith("Marvin Ultimate Casement: CN 2864: Gordium filled the clear opening from Marvin UCA UCANF-25 (PDF page 27)" +
                          ", Ver 2019.3 2019-06-24: confirm it (check the hinge/hardware: the formulas are Marvin's \"with Standard Screen\"", p.Line);
        Assert.Contains("wash/egress hinge", p.Line);
        Assert.DoesNotContain("meets", p.Line);                  // a maker's E mark is never said as a pass
    }

    [Fact]
    public void A_type_with_any_value_the_architect_typed_or_a_stamp_is_never_filled()
    {
        var typed = new Dictionary<Guid, MarkValue> { [Marks.ClearWidth.Guid] = new(true, Number: 2.0) };
        Assert.Empty(ClearPrefills.Plan(Model(Window("a", type: typed))));
        var source = new Dictionary<Guid, MarkValue> { [Marks.ClearSource.Guid] = new(true, Text: "Marvin ADM, my reading") };
        Assert.Empty(ClearPrefills.Plan(Model(Window("a", type: source))));
        var stamped = new Dictionary<Guid, MarkValue> { [Marks.ClearConfirmed.Guid] = new(true, Text: "{}") };
        Assert.Empty(ClearPrefills.Plan(Model(Window("a", type: stamped))));
        // blank marks (a parameter Revit has, never set) are empty: filled
        var blank = new Dictionary<Guid, MarkValue>
        {
            [Marks.ClearWidth.Guid] = new(false), [Marks.ClearHeight.Guid] = new(false), [Marks.ClearSource.Guid] = new(true, Text: " "),
        };
        Assert.Equal(PrefillState.Fill, Assert.Single(ClearPrefills.Plan(Model(Window("a", type: blank)))).State);
    }

    [Fact]
    public void Once_written_it_reads_as_gordiums_draft_and_a_resized_type_is_said_to_differ()
    {
        var fill = ClearPrefills.Plan(Model(Window("a")))[0];
        var written = new Dictionary<Guid, MarkValue>
        {
            [Marks.ClearWidth.Guid] = new(true, Number: fill.ClearWidth), [Marks.ClearHeight.Guid] = new(true, Number: fill.ClearHeight),
            [Marks.ClearSource.Guid] = new(true, Text: fill.Source),
        };
        var again = Assert.Single(ClearPrefills.Plan(Model(Window("a", type: written))));
        Assert.Equal(PrefillState.Filled, again.State);
        Assert.Null(again.ClearWidth);                           // nothing written twice
        Assert.Equal(fill.Line, again.Line);
        var resized = Assert.Single(ClearPrefills.Plan(Model(Window("a", w: 32, type: written))));
        Assert.Equal(PrefillState.Differs, resized.State);
        Assert.Contains("resized", resized.Line);
    }

    [Fact]
    public void No_match_asks_as_before_and_a_known_maker_is_named_with_its_pdf()
    {
        Assert.Empty(ClearPrefills.Plan(Model(Window("a", maker: "Acme Windows"))));
        Assert.Empty(ClearPrefills.Plan(Model(Window("a", maker: null, model: null))));
        var andersen = Assert.Single(ClearPrefills.Plan(Model(Window("a", maker: "Andersen", model: "400 Series"))));
        Assert.Equal(PrefillState.KnownMakerOnly, andersen.State);
        Assert.Contains("https://www.andersenwindows.com/-/media/aw/files/technical-docs/sizing/sizing-windows--a-series-hung.pdf", andersen.Line);
        Assert.Null(andersen.ClearWidth);
        var rough = Assert.Single(ClearPrefills.Plan(Model(Window("a", w: 29, h: 63.625))));
        Assert.Equal(PrefillState.NotFilled, rough.State);
        Assert.Contains("rough opening", rough.Line);
        // a door type is never filled from a window's formula
        var door = Window("d") with { BuiltInCategory = Marks.Doors };
        Assert.Empty(ClearPrefills.Plan(Model(door)));
    }

    [Fact]
    public void The_marking_list_shows_the_line()
    {
        var list = MarkingList.Build(Model(Window("a")));
        Assert.Contains(list.ClearLines, l => l.Contains("Gordium filled the clear opening from Marvin"));
        Assert.Contains("Gordium filled the clear opening from Marvin", MarkingList.Text(list));
    }

    [Fact]
    public void A_prefilled_window_sends_no_clear_opening_until_the_architect_confirms_it()
    {
        // house 5's escape window we2, its marks emptied and its type made a Marvin CN 2864 (a row Marvin marks E)
        var house = FakeHouse.Draw("5_basement_window_well");
        var m = house.MarkedIndex("we2");
        var o = house.OpeningIndex("we2");
        foreach (var mark in new[] { Marks.ClearWidth, Marks.ClearHeight, Marks.ClearSource, Marks.ClearConfirmed })
            house.SetType("we2", mark, null);
        house.Marked[m] = house.Marked[m] with
        {
            TypeManufacturer = "Marvin", TypeModel = "Ultimate Casement", TypeWidth = 28.0 / 12, TypeHeight = 63.125 / 12,
        };
        house.Openings[o] = house.Openings[o] with { TypeWidth = 28.0 / 12, TypeHeight = 63.125 / 12 };
        var p = ClearPrefills.Plan(house.Model()).Single(x => x.TypeId == house.Marked[m].TypeUniqueId);
        Assert.Equal(PrefillState.Fill, p.State);
        house.SetType("we2", Marks.ClearWidth, new MarkValue(true, Number: p.ClearWidth));
        house.SetType("we2", Marks.ClearHeight, new MarkValue(true, Number: p.ClearHeight));
        house.SetType("we2", Marks.ClearSource, new MarkValue(true, Text: p.Source));
        var read = InteriorReader.Read(house.Model());
        var we2 = read.Interior["openings"]!.AsArray().Single(x => x!["id"]!.GetValue<string>() == FakeHouse.Uid("we2"))!;
        Assert.Null(we2["stated_clear"]);
        Assert.Contains("isn't confirmed", read.Notes.Single(n => n.Part == FakeHouse.Uid("we2") && n.Field == "stated_clear").Why);
        // so its clear opening needs review, never a pass
        Assert.Contains(InteriorTests.Problems(house, read), x => x.Contains("we2 opening_net_clear_area not measured"));
    }
}
