using Gordium.Worker;
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
        var (fill, why) = ClearPrefills.Compute(Marvin, 28.0 / 12, 63.125 / 12, "UCA2864");
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
    public void A_type_matches_on_its_manufacturer_and_window_type_ignoring_case_or_an_exact_call_number_model()
    {
        // Marvin's own family: Manufacturer "Marvin Windows and Doors", shared Window Type "Ultimate Casement", Model the
        // call number ("UCA3648"); either the Window Type or a call-number Model matches, with the Manufacturer
        Assert.Same(Marvin, MakerClearOpenings.Match("Marvin Windows and Doors", "Ultimate Casement", "UCA3648"));
        Assert.Same(Marvin, MakerClearOpenings.Match(" marvin windows and doors ", "ULTIMATE CASEMENT", null));
        Assert.Same(Marvin, MakerClearOpenings.Match("Marvin Windows and Doors", null, "UCA3648"));
        Assert.Null(MakerClearOpenings.Match("Marvin Windows and Doors", "Ultimate Casement - Tripane", "3648 CSMT"));
        Assert.Null(MakerClearOpenings.Match("Marvin Windows and Doors", "Ultimate Casement Push Out", "UCAPO3648"));
        Assert.Null(MakerClearOpenings.Match("Marvin Windows and Doors", null, "Ultimate Casement"));   // a Model naming the line: no longer
        Assert.Null(MakerClearOpenings.Match("Marvin Inc", "Ultimate Casement", "UCA3648"));
        Assert.Null(MakerClearOpenings.Match(null, "Ultimate Casement", "UCA3648"));
        // review round 4: the call number is matched exactly as Marvin writes it, case and all (the design note says so)
        Assert.Null(Marvin.CallNumber("uca3648"));
        Assert.Equal(("36", "48"), Marvin.CallNumber("UCA3648"));
        Assert.Null(MakerClearOpenings.Match("Marvin Windows and Doors", null, null));
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

    // Marvin's family's own shared parameters (Window-Casement-Marvin-Ultimate.rfa's PartAtom, 2026-11-20)
    private static readonly Guid WindowType = new("eafa4376-701d-423a-906c-e9e76dd752ca");
    private static readonly Guid VentArea = new("0d21ad7d-0db0-489a-a1fa-10d502d650b7");

    /// <summary>A window type as Marvin's family gives it (default: CN 2864, frame 28 x 63 1/8 in, no Vent Area).</summary>
    private static MarkedElement Window(string id, string? maker = "Marvin Windows and Doors", string? model = "UCA2864",
                                        double w = 28, double h = 63.125, Dictionary<Guid, MarkValue>? type = null,
                                        string? windowType = "Ultimate Casement", double? vent = null) => new()
    {
        UniqueId = id, BuiltInCategory = Marks.Windows, Name = "CN 2864", Family = "Marvin Ultimate Casement",
        TypeUniqueId = "t-" + id, TypeManufacturer = maker, TypeModel = model, TypeWidth = w / 12, TypeHeight = h / 12,
        Type = type ?? new Dictionary<Guid, MarkValue>(),
        TypeShared = new Dictionary<Guid, MarkValue>
        {
            [WindowType] = new(windowType is not null, Text: windowType),
            [VentArea] = new(vent is not null, Number: vent),
        },
    };

    private static RevitModel Model(params MarkedElement[] e) => new() { Document = "house.rvt", Marked = e };

    [Fact]
    public void Marvins_uca3648_as_its_family_gives_it_is_filled_and_its_vent_area_agrees()
    {
        // the catalog row "UCA3648,Marvin Windows and Doors,Ultimate Casement,36,48,Yes,DP50,3648 CSMT,UCA3648"; Width
        // 3'-0", Height 3'-11 1/8" (the frame); Vent Area 8.43 SF. Its "Egress Window" Yes is never read.
        Assert.Equal(["eafa4376-701d-423a-906c-e9e76dd752ca", "0d21ad7d-0db0-489a-a1fa-10d502d650b7"],
                     MakerClearOpenings.SharedParameters.Select(g => g.ToString()));
        var e = Window("a", model: "UCA3648", w: 36, h: 47.125, vent: 8.43) with { Name = "UCA3648" };
        var p = Assert.Single(ClearPrefills.Plan(Model(e)));
        Assert.Equal(PrefillState.Fill, p.State);
        Assert.Equal(28.875, p.ClearWidth!.Value * 12, 9);
        Assert.Equal(42.0, p.ClearHeight!.Value * 12, 9);
        Assert.Equal(8.42, Math.Round(p.ClearWidth.Value * p.ClearHeight.Value, 2));
        // by its Model alone (no Window Type), too
        Assert.Equal(PrefillState.Fill, Assert.Single(ClearPrefills.Plan(Model(e with
        {
            TypeShared = new Dictionary<Guid, MarkValue> { [VentArea] = new(true, Number: 8.43) },
        }))).State);
    }

    [Fact]
    public void A_vent_area_that_disagrees_with_the_formula_stops_the_fill_and_says_why()
    {
        var p = Assert.Single(ClearPrefills.Plan(Model(Window("a", model: "UCA3648", w: 36, h: 47.125, vent: 8.46))));
        Assert.Equal(PrefillState.NotFilled, p.State);
        Assert.Contains("disagrees with the family's own Vent Area (8.46 sq ft)", p.Line);
        Assert.Equal(PrefillState.Fill, Assert.Single(ClearPrefills.Plan(Model(Window("a", model: "UCA3648", w: 36, h: 47.125, vent: 8.44)))).State);
    }

    [Fact]
    public void A_call_number_model_that_isnt_the_types_frame_is_never_filled()
    {
        // Marvin's mulled families carry the same Window Type and one unit's Model: a 2-wide of CN 16 units, 32 in wide
        var p = Assert.Single(ClearPrefills.Plan(Model(Window("a", model: "UCA1664", w: 32, h: 63.125))));
        Assert.Equal(PrefillState.NotFilled, p.State);
        Assert.Contains("is a call number whose frame isn't its Width and Height", p.Line);
        Assert.Equal(PrefillState.NotFilled, Assert.Single(ClearPrefills.Plan(Model(Window("a", model: "UCA9964")))).State);
    }

    [Fact]
    public void An_empty_matching_type_is_filled_as_a_draft_naming_the_maker_page_and_formula()
    {
        var p = Assert.Single(ClearPrefills.Plan(Model(Window("a"), Window("b") with { TypeUniqueId = "t-a" })));   // once per type
        Assert.Equal(PrefillState.Fill, p.State);
        Assert.Equal(20.875 / 12, p.ClearWidth!.Value, 12);
        Assert.Equal(58.0 / 12, p.ClearHeight!.Value, 12);
        Assert.StartsWith(ClearPrefills.SourcePrefix + "Marvin Ultimate Casement (UCA), full frame, UCA UCANF-25 (PDF page 27)", p.Source);
        Assert.EndsWith("clear width = frame width - 7.125 in, clear height = frame height - 5.125 in; frame 28 in by 63.125 in " +
                        "(the type's Width and Height, call number UCA2864).", p.Source);
        // the source is sent as stated_clear.source once confirmed: facts only, never "draft" (review round 1)
        Assert.DoesNotContain("draft", p.Source, StringComparison.OrdinalIgnoreCase);
        // not yet written: "will fill", never "filled" (a write Revit rolls back leaves it so: review round 1)
        Assert.StartsWith("Marvin Ultimate Casement: CN 2864: Gordium will fill the clear opening from Marvin UCA UCANF-25 (PDF page 27)" +
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
        Assert.DoesNotContain("Gordium filled", fill.Line);
        Assert.Equal(fill.Line.Replace("Gordium will fill", "Gordium filled"), again.Line);
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
        Assert.Contains(list.ClearLines, l => l.Contains("Gordium will fill the clear opening from Marvin"));
        Assert.Contains("Gordium will fill the clear opening from Marvin", MarkingList.Text(list));
    }

    // ---- review round 2 -----------------------------------------------------------------------------------------

    [Fact]
    public void A_failed_write_is_said_in_the_dialog_and_the_list_never_says_will_fill()
    {
        const string why = "Revit's transaction ended RolledBack";
        Assert.Equal("Gordium couldn't write the makers' clear openings (Revit's transaction ended RolledBack): fill them by " +
                     "hand from the maker's tables; until then their clear opening needs review.\n\n", ClearPrefills.Head(0, why));
        Assert.Equal("", ClearPrefills.Head(0, null));
        Assert.StartsWith("Gordium filled the maker's clear opening of 2 window types", ClearPrefills.Head(2, null));
        var p = Assert.Single(ClearPrefills.Plan(Model(Window("a")), writeFailed: why));
        Assert.Equal(PrefillState.NotFilled, p.State);
        Assert.Null(p.ClearWidth);
        Assert.Contains("Gordium couldn't write its clear opening from Marvin", p.Line);
        Assert.Contains("until then its clear opening needs review", p.Line);
        Assert.DoesNotContain("will fill", p.Line);
        Assert.DoesNotContain("confirm it", p.Line);
        var list = MarkingList.Build(Model(Window("a")), clearWriteFailed: why);
        Assert.DoesNotContain("will fill", MarkingList.Text(list));
        Assert.Contains("Gordium couldn't write its clear opening", MarkingList.Text(list));
    }

    [Fact]
    public void A_gordium_draft_on_a_type_that_no_longer_matches_is_never_called_typed()
    {
        var fill = ClearPrefills.Plan(Model(Window("a")))[0];
        var written = new Dictionary<Guid, MarkValue>
        {
            [Marks.ClearWidth.Guid] = new(true, Number: fill.ClearWidth), [Marks.ClearHeight.Guid] = new(true, Number: fill.ClearHeight),
            [Marks.ClearSource.Guid] = new(true, Text: fill.Source),
        };
        // the Model and Window Type changed (another Marvin line), and then the Manufacturer too
        foreach (var maker in new[] { "Marvin Windows and Doors", "Acme Windows" })
        {
            var p = Assert.Single(ClearPrefills.Plan(Model(Window("a", maker: maker, model: "UCAPO2864", windowType: "Ultimate Casement Push Out", type: written))));
            Assert.Equal(PrefillState.Differs, p.State);
            Assert.Contains("was filled by Gordium from Marvin Ultimate Casement (UCA) earlier, but the type no longer matches", p.Line);
            Assert.DoesNotContain("as typed on it", p.Line);
        }
    }

    // ---- review round 1 -----------------------------------------------------------------------------------------

    [Fact]
    public void A_write_revit_rolled_back_counts_nothing_as_filled()
    {
        var todo = ClearPrefills.Plan(Model(Window("a")));
        Assert.Empty(ClearPrefills.Written(todo, committed: false));
        Assert.Equal(todo, ClearPrefills.Written(todo, committed: true));
        // review round 3: the outcome from Revit's TransactionStatus, its reason shown by the dialog and the list
        var (none, why) = ClearPrefills.Outcome(todo, "RolledBack");
        Assert.Empty(none);
        Assert.Equal("Revit's transaction ended RolledBack", why);
        var (all, ok) = ClearPrefills.Outcome(todo, "Committed");
        Assert.Equal(todo, all);
        Assert.Null(ok);
    }

    [Fact]
    public void The_add_in_shows_a_failed_write_in_both_dialogs_and_the_marking_list()
    {
        // review round 3: the Revit layer's call sites, read as text (the Revit layer isn't built on the test machine's
        // reference set), each passing the failure on
        string Src(string file) => File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", file));
        var marks = Src("RevitMarks.cs");
        Assert.Contains("ClearPrefills.Outcome(todo, t.Commit().ToString())", marks);
        Assert.Contains("var (filled, failed) = RevitMarks.TryPrefill(doc, model, log);", marks);
        Assert.Contains("MarkingList.Build(model, plan, clearWriteFailed: failed)", marks);
        Assert.Contains("ClearPrefills.Head(filled.Count, failed)", marks);
        var check = Src("CheckProject.cs");
        Assert.Contains("var (filled, failed) = RevitMarks.TryPrefill(doc, RevitMarks.Model(doc), log);", check);
        // the results panel (PR #136): the words go to the panel's status line and first into check_project_result.txt,
        // and the fill runs before the street ask
        Assert.Contains("            clear = ClearPrefills.Head(filled.Count, failed);", check);
        // (PR 8: what to fill in shown from the read; the answer's run, with the read's clear words, when it arrives)
        // (the Setup form, 2026-11-22: nothing sent shows the form, saying why after the clear words)
        Assert.Contains("SetupRun.Show(ui, doc, notice: clear + SetupWords.NothingSent(", check);
        Assert.Contains("check.Read(prepared, added.Count, ask, clear);", check);
        Assert.Contains("Show(ui, doc, run, check.MarksAdded, check.Ask, check.Clear, check.ReadAt, stale: use == AnswerUse.ShowStale);", check);
        Assert.Contains("File.WriteAllText(file, clear + run.FullText + \"\\n\"", check);
        Assert.Contains("ClearWords: clear", check);
        Assert.True(check.IndexOf("RevitMarks.TryPrefill(", StringComparison.Ordinal) < check.IndexOf("StreetEdges.Ask(", StringComparison.Ordinal));
        var view = Src("ResultsView.cs");
        Assert.Contains("ClearPrefills.PanelStatus(content.MarksAdded, content.ClearWords, stale: content.Model?.Stale is not null)", view);
        // review round 7: a check that fails after the drafts were written still says so, in the panel and the dialog
        // (UI polish PR 5: the failure is one card in the pane, no dialog; the words written before it are on screen,
        // under the card's words, for a read that fails, a check that fails, and a checker that stops)
        Assert.Contains("ResultsPane.Failed(CheckFailures.OfRead(e, clear + $\"Nothing was checked", check);
        // each failure: its own statement says what was written and whether anything was, and brings the pane up first
        var calls = check.Split("ResultsPane.Failed(")[1..];
        Assert.Equal(3, calls.Length);
        foreach (var call in calls)
            Assert.Contains(".After(ClearPrefills.StatusLine(", call[..call.IndexOf(';')], StringComparison.Ordinal);
        Assert.Equal(3, check.Split("ResultsPane.Reveal(ui);").Length - 1);
        var reveal = Src("ResultsPane.cs");
        reveal = reveal[reveal.IndexOf("internal static void Reveal(UIApplication ui)", StringComparison.Ordinal)..];
        reveal = reveal[..reveal.IndexOf("\n    }\n", StringComparison.Ordinal)];
        Assert.Contains("ui.GetDockablePane(Id).Show();", reveal, StringComparison.Ordinal);     // best effort: never stops the card
        Assert.Contains("catch (Exception e) when (e is Autodesk.Revit.Exceptions.ApplicationException or InvalidOperationException)", reveal, StringComparison.Ordinal);
        // the fourth failure card, Revit not taking the next step after the read, says what the read wrote too
        Assert.Contains(".After(ClearPrefills.StatusLine(MarksAdded, Clear), Wrote));", Src("CheckRun.cs"), StringComparison.Ordinal);
        Assert.Contains("CheckFailures.NotStarted($\"Revit didn't take {what}: nothing was checked.\", afterRead: Prepared is not null)", Src("CheckRun.cs"), StringComparison.Ordinal);
        foreach (var wrote in new[] { "check.Wrote = added.Count > 0;", "check.Wrote |= filled.Count > 0;", "check.Wrote = true;" })
            Assert.Contains(wrote, check);
        Assert.Equal(2, check.Split("check.Wrote = true;").Length - 1);                 // each street pick
        var failedView = view[view.IndexOf("    internal void Failed(CheckFailure? failure)", StringComparison.Ordinal)..];
        Assert.Contains("if (failure.Done is { } done)                           // what was already written to the project, on screen\n            card.Children.Add(Small(done, top: 4));",
                        failedView.Replace("\r\n", "\n"), StringComparison.Ordinal);
        // what was written, said on screen; nothing written: nothing said, and the model's claim kept
        var read = CheckFailures.OfRead(new InvalidOperationException("x"), "d");
        var after = read.After(ClearPrefills.StatusLine(3, ClearPrefills.Head(2, null)), wrote: true);
        Assert.Equal("Added 3 Gordium marks to this project. " + ClearPrefills.Head(2, null).Trim(), after.Done);
        Assert.DoesNotContain("wasn't changed", after.Words, StringComparison.Ordinal);
        Assert.Contains("nothing was checked", after.Words, StringComparison.OrdinalIgnoreCase);
        var none = read.After(ClearPrefills.StatusLine(0, ""), wrote: false);
        Assert.Null(none.Done);
        Assert.Equal(read.Words, none.Words);
        Assert.Contains("wasn't changed", none.Words, StringComparison.Ordinal);
        // every failure card's claim is dropped once something was written
        foreach (var e in new Exception[] { new InvalidOperationException("x"), new WorkerUnavailableException("x", new InvalidOperationException("y")),
                                            new WorkerExitedException("x", 1, ""), new WorkerTimeoutException("x"), new WorkerStoppedException("x") })
            Assert.DoesNotContain("wasn't changed", CheckFailures.Of(e, "d").After(null, wrote: true).Words, StringComparison.Ordinal);
        // a write that failed: Revit's words never on screen, only in the details
        var raw = ClearPrefills.Head(0, "Autodesk.Revit.Exceptions.ModificationForbiddenException: boom; nothing was written");
        var onScreen = read.After(ClearPrefills.StatusLine(0, raw), wrote: false).Done!;
        Assert.DoesNotContain("boom", onScreen, StringComparison.Ordinal);
        Assert.StartsWith("Gordium couldn't write the makers' clear openings: fill them by hand", onScreen, StringComparison.Ordinal);
        Assert.True(check.IndexOf("var clear = \"\";", StringComparison.Ordinal) < check.IndexOf("        try", StringComparison.Ordinal));
    }

    [Fact]
    public void A_stale_panel_drops_this_runs_marks_and_clear_openings_line()
    {
        var words = ClearPrefills.Head(2, null);
        Assert.Equal("", ClearPrefills.PanelStatus(3, words, stale: true));
        Assert.Equal(ClearPrefills.StatusLine(3, words), ClearPrefills.PanelStatus(3, words, stale: false));
    }

    [Fact]
    public void The_panels_status_line_says_the_marks_added_and_the_clear_openings_words()
    {
        const string why = "Revit's transaction ended RolledBack";
        Assert.Equal("Added 3 Gordium marks to this project. Gordium couldn't write the makers' clear openings (" + why +
                     "): fill them by hand from the maker's tables; until then their clear opening needs review.",
                     ClearPrefills.StatusLine(3, ClearPrefills.Head(0, why)));
        Assert.StartsWith("Gordium filled the maker's clear opening of 1 window type", ClearPrefills.StatusLine(0, ClearPrefills.Head(1, null)));
        Assert.Equal("Added 3 Gordium marks to this project.", ClearPrefills.StatusLine(3, ClearPrefills.Head(0, null)));
        Assert.Equal("", ClearPrefills.StatusLine(0, ""));
    }

    private static Dictionary<Guid, MarkValue> Op(string word) => new() { [Marks.Operation.Guid] = new(true, Text: word) };

    [Fact]
    public void The_formula_is_used_only_for_its_operation_and_an_unset_operation_is_asked_for()
    {
        var hopper = Assert.Single(ClearPrefills.Plan(Model(Window("a", type: Op("Hopper")))));
        Assert.Equal(PrefillState.NotFilled, hopper.State);
        Assert.Contains("its Gordium: Operation is \"Hopper\", but Marvin's formula is for a Casement", hopper.Line);
        var casement = Assert.Single(ClearPrefills.Plan(Model(Window("a", type: Op("casement")))));
        Assert.Equal(PrefillState.Fill, casement.State);
        Assert.DoesNotContain("Set its Gordium: Operation", casement.Line);
        var unset = Assert.Single(ClearPrefills.Plan(Model(Window("a"))));
        Assert.Equal(PrefillState.Fill, unset.State);
        Assert.EndsWith("Set its Gordium: Operation to Casement (the formula is for one).", unset.Line);
        // a draft written, then the operation changed: no longer what Gordium would fill
        var written = new Dictionary<Guid, MarkValue>(Op("Awning"))
        {
            [Marks.ClearWidth.Guid] = new(true, Number: unset.ClearWidth), [Marks.ClearHeight.Guid] = new(true, Number: unset.ClearHeight),
            [Marks.ClearSource.Guid] = new(true, Text: unset.Source),
        };
        Assert.Equal(PrefillState.Differs, Assert.Single(ClearPrefills.Plan(Model(Window("a", type: written)))).State);
    }

    [Fact]
    public void A_known_makers_line_says_what_its_marks_hold()
    {
        var empty = Assert.Single(ClearPrefills.Plan(Model(Window("a", maker: "Andersen", model: "400 Series"))));
        Assert.Contains("take its clear opening from Andersen's clear-opening tables", empty.Line);
        var typed = new Dictionary<Guid, MarkValue> { [Marks.ClearWidth.Guid] = new(true, Number: 2.0) };
        var line = Assert.Single(ClearPrefills.Plan(Model(Window("a", maker: "Andersen", model: "400 Series", type: typed)))).Line;
        Assert.Contains("are as typed on it", line);
        Assert.DoesNotContain("isn't filled", line);
        Assert.DoesNotContain("take its clear opening", line);
    }

    [Fact]
    public void A_window_type_match_without_a_call_number_model_is_never_filled()
    {
        // a mulled unit of two 18 in casements is 36 in overall: a standard frame width, so only the Model tells
        foreach (var model in new string?[] { null, "3648 CSMT", "Ultimate Casement" })
        {
            var p = Assert.Single(ClearPrefills.Plan(Model(Window("a", model: model, w: 36, h: 47.125))));
            Assert.Equal(PrefillState.NotFilled, p.State);
            Assert.Contains("isn't a Marvin call number", p.Line);
        }
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
        house.SetType("we2", Marks.Operation, new MarkValue(true, Text: "Casement"));      // the formula's operation
        house.Marked[m] = house.Marked[m] with
        {
            TypeManufacturer = "Marvin Windows and Doors", TypeModel = "UCA2864", TypeWidth = 28.0 / 12, TypeHeight = 63.125 / 12,
            TypeShared = new Dictionary<Guid, MarkValue> { [WindowType] = new(true, Text: "Ultimate Casement") },
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
