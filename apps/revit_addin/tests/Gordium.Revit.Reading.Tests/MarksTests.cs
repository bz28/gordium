using System.Diagnostics;
using System.Text.Json;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The architect's marks (docs/revit/revit_interior_reading_design.md, sections 2, 3 and 5a; section 7,
/// step 2): the shared parameters as data, adding them to a project, reading them (an unset mark is not stated,
/// never No), and the marking list (unset first; a room name only ever a suggestion). Each is pinned on fake records;
/// that Revit's API gives what the records say (an unset Yes/No's <c>HasValue</c> false, on old and new elements) is
/// for the trial to confirm.</summary>
public sealed class MarksTests
{
    // ---- the parameters, as the design note's table -------------------------------------------------------------

    [Fact]
    public void The_marks_are_the_design_notes_table_and_their_guids_never_change()
    {
        // a changed GUID is a different parameter: every mark set on the old one would read as not set
        var expected = new (string Name, string Guid, MarkValueKind Kind, MarkBinding Binding, string[] Categories)[]
        {
            ("Gordium: Sleeping room", "938333c3-b268-495a-8835-5c667a514122", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_Rooms"]),
            ("Gordium: Escape opening", "04893afb-a562-4d71-b5c9-28c4e9541060", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_Windows", "OST_Doors"]),
            ("Gordium: Exit door", "ba0a9f39-5bce-4e05-98f9-15b639b9eb2a", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_Doors"]),
            ("Gordium: Operation", "7b1e6d97-1774-458d-8f46-90002a1881c0", MarkValueKind.Text, MarkBinding.Type, ["OST_Windows", "OST_Doors"]),
            // step 5: a door type's maker's clear opening too (no offset: a door's clear opening has no bottom sent)
            ("Gordium: Clear width", "8cb5d70c-116d-4621-9876-fd15c4c55f5c", MarkValueKind.Length, MarkBinding.Type, ["OST_Windows", "OST_Doors"]),
            ("Gordium: Clear height", "8a8a2307-84a5-4a36-9121-c21453707702", MarkValueKind.Length, MarkBinding.Type, ["OST_Windows", "OST_Doors"]),
            ("Gordium: Clear offset", "07f4d517-54a6-4e39-ba85-90c299137a28", MarkValueKind.Length, MarkBinding.Type, ["OST_Windows"]),
            ("Gordium: Clear source", "2bc7eaef-1770-4077-870b-450ed224adde", MarkValueKind.Text, MarkBinding.Type, ["OST_Windows", "OST_Doors"]),
            ("Gordium: Clear confirmed", "66ced3f6-2dd7-4aa7-a0ce-89d086652103", MarkValueKind.Text, MarkBinding.Type, ["OST_Windows", "OST_Doors"]),
            ("Gordium: Top rail is handrail", "8f09dc9e-0975-42ba-8a4b-43e43b393578", MarkValueKind.YesNo, MarkBinding.Type, ["OST_StairsRailing"]),
            ("Gordium: These are all the stairs", "90205a68-1eaf-4ca2-a350-0cb24012986c", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: These are all the guards and handrails", "80055f84-3feb-492a-b581-331ff692a2a9", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            // Check my project's lot facts (reading design note, section 9)
            ("Gordium: Zone", "7c0c478b-5959-44fd-bf53-ca89d9302bf0", MarkValueKind.Text, MarkBinding.Instance, ["OST_ProjectInformation"]),
            // escape routes (section 10): the same parameter on a Room says the room's use (its GUID kept: marks set on
            // Project Information before stay read)
            ("Gordium: Use", "0a732869-f46a-4fbd-bab9-4d60735d96f3", MarkValueKind.Text, MarkBinding.Instance, ["OST_ProjectInformation", "OST_Rooms"]),
            ("Gordium: Lot surveyed", "133d30e3-832f-4956-88c3-6b48989ac3f7", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Corner lot", "b37e1302-284e-4440-bc43-a44309ea8991", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Street edge", "260b3e70-6b9b-45d2-8137-a5c18db9ccf5", MarkValueKind.Text, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Ground from", "aa4ea7e3-5a41-48da-b6a8-979f3dfb3e5c", MarkValueKind.Text, MarkBinding.Instance, ["OST_ProjectInformation"]),
            // step 6: what the house has none of, one tick per kind
            ("Gordium: This house has no stairs", "a1f4e4bd-612e-4ac3-8f40-29734e304311", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: This house has no doors", "06f6906a-a8b1-4ca9-81bc-f073346c5bad", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: This house has no guards", "8ba873c3-cea1-4adc-b301-52e61ba9c1a4", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: This house has no basements", "a96ef278-0a0e-4787-b2ed-0f5e3fd4e693", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: This house has no habitable attics", "bccc5c23-d42d-47cf-bd62-0c45311db280", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: This house has no sleeping lofts", "348c128f-c23b-40af-a0ea-2b1acaa45d46", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: This house has no ramps", "6aad2ebe-4051-49b2-bae3-e531d9d620f4", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: This house has no alternating tread devices", "3e807c15-9890-4ed0-9f16-98ee891af0f1", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: This house has no ship ladders", "0249580f-f83a-431e-9e59-9e9e5a542066", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: This house has no patio covers", "0b28269f-ee8a-4939-b3ed-2ac97d6b44d1", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: This house has no deck or porch or cantilever over an escape opening", "820cd2d1-5b6d-416d-afa8-01cb1f0c4515", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            // a real model (Pacific Continental, 2026-11-20): a roof or turret level whose enclosed areas aren't rooms
            ("Gordium: No rooms on this level", "c8cc09e8-00ce-4e4b-a27a-4c2d23410a02", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_Levels"]),
            // the same model's wall niches, corbels and trim drawn as Generic Models (Q2): cleared one by one
            ("Gordium: Not a stair", "6f527562-6b18-467b-9e86-5a2c5489dbc2", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_GenericModel", "OST_Stairs", "OST_StairsRailing"]),
            // what a floor outside the house is (reading design note, section 1, "Site slabs")
            ("Gordium: Site slab is", "56113427-6ae6-430d-95dd-2472fbefff71", MarkValueKind.Text, MarkBinding.Instance, ["OST_Floors"]),
            // what an object on the lot that isn't the building is (reading design note, section 1, "Objects standing apart")
            ("Gordium: Site object is", "2f1ba96f-363b-4bdb-a03c-832fad615857", MarkValueKind.Text, MarkBinding.Instance,
             ["OST_GenericModel", "OST_SpecialityEquipment", "OST_Site", "OST_Mass", "OST_Furniture", "OST_Casework",
              "OST_StructuralFraming", "OST_StructuralFoundation", "OST_Parking", "OST_MechanicalEquipment",
              "OST_LightingFixtures"]),
            // escape routes (section 10): which rooms a route may cross, and which doors are exits
            ("Gordium: Can be locked", "5b0d7c3e-2f41-4a8e-9c63-1e7a4f2b9d05", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_Rooms"]),
            ("Gordium: Pass through", "c2e94a61-7d3b-4f5e-8a10-6b9d3e2f4c87", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_Rooms"]),
            ("Gordium: Exit", "e7a3c519-04d2-4b86-b1f5-93c8d6a2e470", MarkValueKind.Text, MarkBinding.Instance, ["OST_Doors"]),
            // the architect's count of stories (optional; reading design note, section 9)
            ("Gordium: Stories", "bf758947-8ee4-490c-a499-dee706a6f1e7", MarkValueKind.Integer, MarkBinding.Instance, ["OST_ProjectInformation"]),
            // a space nobody occupies (route note decision 1b)
            ("Gordium: Not occupied", "306bccbe-b2f7-4a73-9169-6be76fb46202", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_Rooms"]),
            // a room's Table 1004.5 function (the Building Code's occupant loads)
            ("Gordium: Function", "de595662-5386-4cab-9245-600eefb9462d", MarkValueKind.Text, MarkBinding.Instance, ["OST_Rooms"]),
            // which New York code governs, and what the Building Code's rules read (docs/decisions/2026-11-22_which_ny_code.md)
            ("Gordium: Follows the Building Code", "01405f95-7061-47e2-b2a3-7706747c0817", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Stories above grade plane", "3f5ba80f-f877-49d9-bc47-a86de4a87a19", MarkValueKind.Integer, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Separate means of egress", "489999a0-b6a0-4d36-a186-a7874e8e78ff", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Townhouse units", "81480188-21b7-4786-b2b3-c3da847439c2", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Care facility", "58d76f42-7618-4c1c-8765-3af6c45b31d2", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Occupancy groups", "ea50d05c-05a2-46b3-aafc-6cbb22bf19ac", MarkValueKind.Text, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Sprinkler system", "4b542577-d04e-463a-87fa-019dbc102374", MarkValueKind.Text, MarkBinding.Instance, ["OST_ProjectInformation"]),
            // what the Building Code's Chapter 10 rules read of the whole building (code_scope.FACTS)
            ("Gordium: Fixed assembly seating", "717d4f32-6264-46b4-95e7-ffd7668518c4", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Special egress spaces", "8efde5e2-df14-4f88-b8ce-da46285b930d", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Merchandise pads", "90d6a3a4-6f52-487c-b98b-21ea864dee45", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Egress balcony increase", "3f260842-2450-44da-902d-3e066984a521", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: R-2 sleeping units", "b8d986fc-ae44-428a-8740-0937a6a8197a", MarkValueKind.Text, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: 1031 escape openings", "298cd307-3a3f-4c2f-a12d-e8fe3d31b4f6", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Atrium", "8c3211a5-546b-463e-8d8c-b70fd753c1b6", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            // group 3's (1004.7, 1004.5.1)
            ("Gordium: Occupied outdoor areas", "5be49bb1-7c0f-4eea-a360-c6b47d2e9dad", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Occupant load increased", "64b5a6c7-d4ae-4424-b7e1-2c041b09d02a", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            // groups 4 and 5's (1020 corridors, 1005.3 capacity)
            ("Gordium: Other levels reach corridors", "63ce1aaf-5fb8-4af6-9c71-730392b78bb4", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Ambulatory care facility", "2a31e2c4-cf29-4ac4-9c57-a41ca85748b3", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Corridors within dwelling units", "a61d6738-cc50-4a7a-bf34-eb258e6b55d7", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Emergency voice/alarm system", "f4184d32-275e-4423-90c6-66a2e4d247ee", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Mezzanines", "c2f4615d-5335-49cc-a997-311bac414fbd", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Loads not by area", "501f87dd-fbc9-4ab6-8478-301feeb6d0a8", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            // Chapter 4 part b's (403 high-rise, 405 underground)
            ("Gordium: High-rise building", "50749eaa-b331-40c1-af60-c1bf02acbc28", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Underground building", "0b116213-0d7e-4e3c-b03b-e71a9f387d05", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            // the dwelling's own facts the code decision reads (review round 1: an ask named marks Revit didn't have)
            ("Gordium: Dwelling units", "aa32131a-e757-47a3-abf8-9deb81d7a09a", MarkValueKind.Integer, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Units in the attached building", "bccb088a-c087-475f-9ff9-53fd10133d0e", MarkValueKind.Integer, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Home occupation", "c6a7cf3a-28b8-4c18-98f2-cf34215901bf", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Rooms let for profit", "2f038e8d-2d26-4e46-b92a-1c51d08bca87", MarkValueKind.Integer, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Accessory dwelling unit", "6fcbf10d-a1c2-406a-b6c7-e726b4a695f2", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: ADU detached", "ebd07d28-ce47-4e7d-95e7-6e164d7d7bc8", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: ADUs on parcel", "1fa82254-92d5-4f27-acef-924bfc047d7c", MarkValueKind.Integer, MarkBinding.Instance, ["OST_ProjectInformation"]),
            // the house's own facts Ithaca's zoning reads (UI design change 20: the house's fix cards had no button)
            ("Gordium: Stream within 20 ft", "17620cff-9a18-449f-900b-cd66e0ed1b82", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Distance from stream", "6b203698-192c-4814-b27c-4e5968fa8111", MarkValueKind.Length, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Unrelated people per unit", "74a581ac-f1c6-4062-a97f-0504955d2175", MarkValueKind.Integer, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Owner-occupied", "489c2902-38ec-430f-aa5e-47675cb48eff", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Functional family unit", "868efeab-7254-4c46-bf04-564a4c853946", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Garage cars", "08e37847-735e-417a-85fa-fb945a28276f", MarkValueKind.Integer, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Private garages", "92d7674d-e182-407c-a43b-2acb0146265b", MarkValueKind.Integer, MarkBinding.Instance, ["OST_ProjectInformation"]),
            // the lot facts the worker's cards asked for with no mark to set (an area: a new kind, square feet inside)
            ("Gordium: Abuts R-1 land", "e03a7668-69f3-4286-b79e-7e2fedd51174", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Conversion", "b4ae661a-9d9d-4e7b-addf-cb674911fc28", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Primary buildings", "99739cee-bd25-46a2-9ed4-f552654d1209", MarkValueKind.Integer, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Primary buildings same use", "8c4cda53-f475-42ff-ad64-b7ba1f85979e", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Home occupation area", "78decf20-6a2b-49f3-910c-c09c2e63d90d", MarkValueKind.Area, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Home occupation unit area", "2b6debca-6222-4c69-a0b0-c6d754ef4f0d", MarkValueKind.Area, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: ADU in existing building", "acd7b1f8-d8f1-4001-8a07-362db5e75524", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: ADU bedrooms", "019161da-e9c1-4219-8cfc-01dbd1071761", MarkValueKind.Integer, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: ADU floor area", "41c8f63d-368d-4ea9-b371-85828b769d6a", MarkValueKind.Area, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Main building floor area", "f237131b-5e7e-4c8e-94df-a8538de16954", MarkValueKind.Area, MarkBinding.Instance, ["OST_ProjectInformation"]),
            // a door type's leaves (BCNYS 1010.1.1: one leaf of a pair with no mullion gives the 32 in)
            ("Gordium: Leaves", "f23ad40b-e048-4b61-a92a-b7963e64d4cf", MarkValueKind.Integer, MarkBinding.Type, ["OST_Doors"]),
            // what latches or locks each door (BCNYS 1010.2.8): no door family or type parameter says it
            ("Gordium: Hardware", "9900f8fa-52dd-4654-bda2-1e1a4b9cb959", MarkValueKind.Text, MarkBinding.Instance, ["OST_Doors"]),
            // the Toposolids show the finished ground (RCNYS R202 GRADE): only then is the ground at each window read
            ("Gordium: Toposolid is finished ground", "bbb69f1e-d644-4830-8ba0-cd958c04bbb8", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            // an escape opening below grade and its area well (BCNYS 1031.5): a well isn't in Revit's vocabulary
            ("Gordium: Below grade", "250e27a5-d58b-4ddf-8ece-b35235ccc1f2", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_Windows", "OST_Doors"]),
            ("Gordium: Well area", "6e368439-8dd1-48c8-99bf-eff9afd45b39", MarkValueKind.Area, MarkBinding.Instance, ["OST_Windows", "OST_Doors"]),
            ("Gordium: Well width", "6305ccee-e00f-4870-868f-e58241f9a0ef", MarkValueKind.Length, MarkBinding.Instance, ["OST_Windows", "OST_Doors"]),
            ("Gordium: Well projection", "8814e090-d06c-467c-ae0f-c0518835997f", MarkValueKind.Length, MarkBinding.Instance, ["OST_Windows", "OST_Doors"]),
            ("Gordium: Well depth", "8aba2fba-b56c-4825-ab0f-86247ec221c8", MarkValueKind.Length, MarkBinding.Instance, ["OST_Windows", "OST_Doors"]),
            ("Gordium: Well ladder or steps", "a9a70071-4f69-40e0-9db5-a713f65b7e6a", MarkValueKind.Text, MarkBinding.Instance, ["OST_Windows", "OST_Doors"]),
            ("Gordium: Well ladder width", "2cfc1b61-245d-4783-afab-6eefd4fae35a", MarkValueKind.Length, MarkBinding.Instance, ["OST_Windows", "OST_Doors"]),
            ("Gordium: Well rung projection", "18694498-b560-4e59-95ac-a555e05d71ec", MarkValueKind.Length, MarkBinding.Instance, ["OST_Windows", "OST_Doors"]),
            ("Gordium: Well rung spacing", "a380f476-72bc-4ee8-9720-296d49313a30", MarkValueKind.Length, MarkBinding.Instance, ["OST_Windows", "OST_Doors"]),
            ("Gordium: Well step tread", "8b6628e2-2ee7-434e-ad15-b563fa95ccca", MarkValueKind.Length, MarkBinding.Instance, ["OST_Windows", "OST_Doors"]),
            ("Gordium: Well step riser", "444f0f5a-3046-4ce6-91b7-570b5cf3e23c", MarkValueKind.Length, MarkBinding.Instance, ["OST_Windows", "OST_Doors"]),
            ("Gordium: Well ladder full height", "f982cb20-0562-4a16-9cd8-40f8642b9ddb", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_Windows", "OST_Doors"]),
            ("Gordium: Well ladder encroachment", "f9c44848-4643-4aca-a1c2-e073d03694d8", MarkValueKind.Length, MarkBinding.Instance, ["OST_Windows", "OST_Doors"]),
            ("Gordium: Well other encroachment", "961cebf6-451f-4b59-8151-f10eedcf1db5", MarkValueKind.Length, MarkBinding.Instance, ["OST_Windows", "OST_Doors"]),
            // a corridor's walls (the egress UI audit's finding 5, 2026-11-26)
            ("Gordium: Corridor rating minutes", "3e9778e1-4f8d-40cc-a224-58933cb06a45", MarkValueKind.Integer, MarkBinding.Instance, ["OST_Rooms"]),
            ("Gordium: Smoke partition walls", "6a953c28-38f7-49d7-8e3c-5f38cc3aa78c", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_Rooms"]),
        };
        Assert.Equal(expected.Length, Marks.All.Count);
        foreach (var (m, e) in Marks.All.Zip(expected))
        {
            Assert.Equal(e.Name, m.Name);
            Assert.Equal(Guid.Parse(e.Guid), m.Guid);
            Assert.Equal(e.Kind, m.Kind);
            Assert.Equal(e.Binding, m.Binding);
            Assert.Equal(e.Categories, m.Categories);
            Assert.False(string.IsNullOrWhiteSpace(m.Description));
        }
        Assert.Equal(Marks.All.Count, Marks.All.Select(m => m.Guid).Distinct().Count());
        // a GUID that once meant a narrower question is never reused for a wider one: an answer to the old question
        // would read as an answer to the new (review round 3: Gordium: Bowling lanes became Gordium: Loads not by area)
        Guid[] retired = [Guid.Parse("5049ea17-952b-4916-b429-896167244126")];
        Assert.DoesNotContain(Marks.All, m => retired.Contains(m.Guid));
    }

    [Fact]
    public void The_design_note_names_each_mark()
    {
        var note = File.ReadAllText(Path.Combine(Env.Repo, "docs", "revit", "revit_interior_reading_design.md"));
        foreach (var m in Marks.All)
            Assert.Contains(m.Name.Replace("Gordium: ", ""), note);
    }

    [Fact]
    public void The_stories_tooltip_cites_each_words_own_section()
    {
        // review round 1 (2026-11-22): "main entrance side" is 325-8A Column 8's (p.24), never 325-3B STORY's (p.19)
        var d = Marks.Stories.Description;
        var story = d.Substring(d.IndexOf("§325-3B", StringComparison.Ordinal));
        story = story.Substring(0, story.IndexOf(';'));
        Assert.DoesNotContain("main entrance", story, StringComparison.Ordinal);
        Assert.Contains("main entrance side, §325-8A", d, StringComparison.Ordinal);
    }

    [Fact]
    public void No_mark_description_runs_two_sentences_together()
    {
        // review round 2 (2026-11-22): literals joined with + and no space read "Column 8).A basement"
        foreach (var m in Marks.All)
            Assert.False(System.Text.RegularExpressions.Regex.IsMatch(m.Description, @"[.;:)][A-Z]"), m.Name);
    }

    // ---- reading a mark: unset is not stated -------------------------------------------------------------------

    [Fact]
    public void An_unset_yes_no_is_not_stated_never_no()
    {
        Assert.Null(Marks.YesNo(null));                                   // not on the element at all
        Assert.Null(Marks.YesNo(new MarkValue(false, Integer: 0)));       // never set: Revit's AsInteger() gives 0
        Assert.Null(Marks.YesNo(new MarkValue(true)));                    // set, but not an integer
        Assert.Null(Marks.YesNo(new MarkValue(true, Integer: 2)));
        Assert.Null(Marks.YesNo(new MarkValue(true, Text: "Yes")));
        Assert.True(Marks.YesNo(new MarkValue(true, Integer: 1)));
        Assert.False(Marks.YesNo(new MarkValue(true, Integer: 0)));
    }

    [Fact]
    public void An_unset_whole_number_is_not_stated_never_zero()
    {
        Assert.Null(Marks.Count(null));
        Assert.Null(Marks.Count(new MarkValue(false, Integer: 0)));       // never set: Revit's AsInteger() gives 0
        Assert.Null(Marks.Count(new MarkValue(true, Text: "3")));         // another storage: not stated
        Assert.Equal(0, Marks.Count(new MarkValue(true, Integer: 0)));    // a 0 typed is a 0 (ProjectFacts asks again)
        Assert.Equal(3, Marks.Count(new MarkValue(true, Integer: 3)));
    }

    [Fact]
    public void A_blank_length_or_text_is_not_stated_never_zero()
    {
        Assert.Null(Marks.Length(new MarkValue(false, Number: 0)));       // blank Clear offset: never 0
        Assert.Null(Marks.Length(new MarkValue(true, Number: double.NaN)));
        Assert.Null(Marks.Length(new MarkValue(true)));
        Assert.Equal(0.0, Marks.Length(new MarkValue(true, Number: 0)));  // a 0 typed is a 0 (the stamp, step 3, checks it)
        Assert.Null(Marks.Text(new MarkValue(true, Text: "   ")));
        Assert.Null(Marks.Text(new MarkValue(false, Text: "Casement")));
        Assert.Equal("Casement", Marks.Text(new MarkValue(true, Text: " Casement ")));
    }

    // ---- the operation list ---------------------------------------------------------------------------------

    [Fact]
    public void Operation_words_map_to_each_lists_own_word()
    {
        Assert.Equal("side_hinged_door", Operations.ForOpening("Side-hinged door"));
        Assert.Equal("side_hinged", Operations.ForDoor("side-hinged DOOR"));
        Assert.Equal("sliding_door", Operations.ForOpening("Sliding door"));
        Assert.Equal("sliding", Operations.ForDoor("Sliding door"));
        Assert.Equal("other", Operations.ForOpening("Pocket door"));     // no pocket word for an opening: needs the maker's
        Assert.Equal("pocket", Operations.ForDoor("Pocket door"));
        Assert.Equal("double_hung", Operations.ForOpening("Double hung"));
        Assert.Null(Operations.ForDoor("Casement"));                    // a window's word is not a door's
        Assert.Null(Operations.ForOpening("Double-hung"));             // near is not a word: not stated
        Assert.Null(Operations.ForOpening("Casment"));
        Assert.Null(Operations.ForOpening(null));
    }

    [Fact]
    public void Operation_words_reach_exactly_the_measuring_codes_words()
    {
        // the words the measuring code accepts, from its own tables (never retyped)
        var json = Python(
            "import json; from model_measurement.interior import openings, doors; " +
            "print(json.dumps({'opening': list(openings.OPERATIONS), 'door': list(doors.OPERATIONS)}))");
        using var doc = JsonDocument.Parse(json);
        var opening = doc.RootElement.GetProperty("opening").EnumerateArray().Select(e => e.GetString()!).ToHashSet();
        var door = doc.RootElement.GetProperty("door").EnumerateArray().Select(e => e.GetString()!).ToHashSet();
        Assert.Equal(opening, Operations.Words.Select(Operations.ForOpening).ToHashSet()!);
        Assert.Equal(door, Operations.Words.Select(Operations.ForDoor).OfType<string>().ToHashSet());
    }

    private static string Python(string code)
    {
        var info = new ProcessStartInfo(Env.Python)
        {
            WorkingDirectory = Env.Repo, RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false,
        };
        info.ArgumentList.Add("-c");
        info.ArgumentList.Add(code);
        using var p = Process.Start(info)!;
        var err = p.StandardError.ReadToEndAsync();
        var output = p.StandardOutput.ReadToEnd();
        Assert.True(p.WaitForExit(120_000), "python didn't finish");
        Assert.True(p.ExitCode == 0, err.Result);
        return output;
    }

    // ---- adding the marks to a project ----------------------------------------------------------------------

    private static BoundParameter Bound(MarkDefinition m, params string[] categories) =>
        new(m.Name, m.Guid, m.Kind, m.Kind.ToString(), m.Binding == MarkBinding.Instance, categories.Length > 0 ? categories : m.Categories);

    [Fact]
    public void A_new_project_gets_every_mark()
    {
        var plan = MarkSetup.Plan([]);
        Assert.All(plan, s => Assert.Equal(MarkSetupAction.Add, s.Action));
        Assert.Equal(Marks.All, plan.Select(s => s.Mark));
        Assert.Equal(Marks.EscapeOpening.Categories, plan[1].Categories);
    }

    [Fact]
    public void A_project_with_the_marks_is_left_as_it_is()
    {
        var plan = MarkSetup.Plan(Marks.All.Select(m => Bound(m)).ToList());
        Assert.All(plan, s => Assert.Equal(MarkSetupAction.None, s.Action));
    }

    [Fact]
    public void A_missing_category_is_added_and_the_architects_own_are_kept()
    {
        var bound = Marks.All.Select(m => m == Marks.EscapeOpening ? Bound(m, "OST_Windows", "OST_GenericModel") : Bound(m)).ToList();
        var step = MarkSetup.Plan(bound).Single(s => s.Mark == Marks.EscapeOpening);
        Assert.Equal(MarkSetupAction.AddCategories, step.Action);
        Assert.Equal(["OST_Windows", "OST_GenericModel", "OST_Doors"], step.Categories);
    }

    [Fact]
    public void Another_parameter_of_a_marks_name_is_never_taken_for_it()
    {
        var firms = new BoundParameter("gordium: sleeping room", Guid.NewGuid(), MarkValueKind.YesNo, "YesNo", true, ["OST_Rooms"]);
        var plan = MarkSetup.Plan([firms]);
        var step = plan.Single(s => s.Mark == Marks.SleepingRoom);
        Assert.Equal(MarkSetupAction.Conflict, step.Action);
        Assert.Contains("isn't Gordium's", step.Words);
        Assert.Equal(MarkSetupAction.Add, plan.Single(s => s.Mark == Marks.ExitDoor).Action);
        // and the reader reads by GUID: the firm's own Yes is not a mark
        var model = Model(Room("r", "Bedroom", null) with
        {
            Instance = new Dictionary<Guid, MarkValue> { [firms.Guid!.Value] = new(true, Integer: 1) },
        });
        Assert.Null(MarkReading.Rooms(model)!.Single().Sleeping);
    }

    [Fact]
    public void A_mark_bound_the_wrong_way_is_a_conflict_never_rebound()
    {
        var typeBound = Bound(Marks.SleepingRoom) with { IsInstance = false };
        var textKind = Bound(Marks.ExitDoor) with { Kind = MarkValueKind.Text };
        var plan = MarkSetup.Plan([typeBound, textKind]);
        Assert.Equal(MarkSetupAction.Conflict, plan.Single(s => s.Mark == Marks.SleepingRoom).Action);
        Assert.Equal(MarkSetupAction.Conflict, plan.Single(s => s.Mark == Marks.ExitDoor).Action);
        var list = MarkingList.Build(Model(), plan);
        Assert.Equal(2, list.SetupProblems.Count);
        Assert.StartsWith("Can't add Gordium: Sleeping room", MarkingList.Text(list));
    }

    // ---- reading the marks ----------------------------------------------------------------------------------

    private static RevitModel Model(params MarkedElement[] marked) => new() { Document = "house.rvt", Marked = marked };

    private static MarkValue YesNo(bool? v) => v is { } b ? new(true, Integer: b ? 1 : 0) : new(false, Integer: 0);

    private static MarkedElement Room(string id, string? name, bool? sleeping, string? number = null) => new()
    {
        UniqueId = id, BuiltInCategory = Marks.Rooms, Name = name, Number = number, Placement = RoomPlacement.Placed,
        Instance = new Dictionary<Guid, MarkValue> { [Marks.SleepingRoom.Guid] = YesNo(sleeping) },
    };

    private static MarkedElement Window(string id, bool? escape, string? operation) => new()
    {
        UniqueId = id, BuiltInCategory = Marks.Windows, Name = "36 x 48", Family = "Casement", TypeUniqueId = "t-" + id,
        Instance = new Dictionary<Guid, MarkValue> { [Marks.EscapeOpening.Guid] = YesNo(escape) },
        Type = operation is null ? new Dictionary<Guid, MarkValue>()
            : new Dictionary<Guid, MarkValue> { [Marks.Operation.Guid] = new(true, Text: operation) },
    };

    private static MarkedElement Door(string id, bool? escape, bool? exit, string? operation) => new()
    {
        UniqueId = id, BuiltInCategory = Marks.Doors, Name = "36 x 80", Family = "Single-Flush",
        Instance = new Dictionary<Guid, MarkValue>
        {
            [Marks.EscapeOpening.Guid] = YesNo(escape), [Marks.ExitDoor.Guid] = YesNo(exit),
        },
        Type = operation is null ? new Dictionary<Guid, MarkValue>()
            : new Dictionary<Guid, MarkValue> { [Marks.Operation.Guid] = new(true, Text: operation) },
    };

    [Fact]
    public void Marks_are_read_as_set_and_unset_as_not_stated()
    {
        var model = Model(Room("bed", "Bedroom 2", true), Room("living", "Living", false), Room("study", "Study", null),
                          Window("w1", true, "Casement"), Window("w2", null, "Double-hung"),
                          Door("d1", false, true, "Side-hinged door"), Door("d2", false, null, "Casement"));
        Assert.Equal([true, false, null], MarkReading.Rooms(model)!.Select(r => r.Sleeping));
        var openings = MarkReading.Openings(model);
        Assert.Equal([true, null, false, false], openings.Select(o => o.Escape));
        Assert.Equal(["casement", null, "side_hinged_door", null], openings.Select(o => o.Operation));
        var doors = MarkReading.Doors(model);
        Assert.Equal([true, null], doors.Select(d => d.Exit));
        Assert.Equal(["side_hinged", null], doors.Select(d => d.Operation));
    }

    [Fact]
    public void A_bedroom_by_name_alone_is_never_read_as_a_sleeping_room()
    {
        var model = Model(Room("bed", "Bedroom 2", null));
        Assert.Null(MarkReading.Rooms(model)!.Single().Sleeping);
        var cell = MarkingList.Build(model).Rows.Single().Cells.Single(c => c.Mark == Marks.SleepingRoom);
        Assert.Equal(MarkState.Unset, cell.State);
        Assert.StartsWith("suggested: Yes", cell.Suggestion);
    }

    [Fact]
    public void Only_the_design_checked_is_read_and_listed()
    {
        var model = Model(
            Window("now", true, "Casement"),
            Window("demolished", true, "Casement") with { PhaseDemolished = "new" },
            Window("wide", true, "Casement") with { DesignOption = "w2" },
            Window("narrow", true, "Casement") with { DesignOption = "w1" }) with
        {
            Phases = ["existing", "new"],
            OptionSets = [new("wing", "Wing", [new("w1", "Narrow", true), new("w2", "Wide", false)])],
        };
        Assert.Equal(["now", "narrow"], MarkReading.Openings(model).Select(o => o.Id));
        Assert.Equal(["narrow", "now"], MarkingList.Build(model).Rows.Select(r => r.Id).Order());
    }

    // review round 1, finding 2: a room belongs to one phase; an earlier phase's room isn't the design checked
    [Fact]
    public void Only_the_last_phases_rooms_are_read()
    {
        var model = Model(Room("old", "Bedroom", true) with { PhaseCreated = "existing" },
                          Room("now", "Bedroom", true) with { PhaseCreated = "new" },
                          Window("kept", false, "Casement") with { PhaseCreated = "existing" }) with
        {
            Phases = ["existing", "new"],
        };
        Assert.Equal(["now"], MarkReading.Rooms(model)!.Select(r => r.Id));
        Assert.Equal(["kept"], MarkReading.Openings(model).Select(o => o.Id));
        Assert.Equal(["now", "kept"], MarkingList.Build(model).Rows.Select(r => r.Id));
    }

    // review round 1, finding 2: a Room not on the plan blocks every room, listed first, never a row to mark
    [Fact]
    public void An_unplaced_not_enclosed_or_redundant_room_is_a_blocker_not_a_row()
    {
        var model = Model(Room("placed", "Living", false),
                          Room("unplaced", "Bedroom 3", null) with { Placement = RoomPlacement.Unplaced },
                          Room("open", "Den", false) with { Placement = RoomPlacement.NotEnclosed },
                          Room("twice", "Study", false) with { Placement = RoomPlacement.Redundant },
                          Room("unknown", "Hall", false) with { Placement = null });
        Assert.Null(MarkReading.Rooms(model));            // round 2: rooms not read while any blocker exists
        Assert.Equal(["placed"], MarkReading.Rooms(model with { Marked = [model.Marked[0]] })!.Select(r => r.Id));
        Assert.Equal(4, MarkReading.RoomBlockers(model).Count);
        var list = MarkingList.Build(model);
        Assert.Equal(["placed"], list.Rows.Select(r => r.Id));
        Assert.Equal(
        [
            "Room \"Bedroom 3\": not placed: place it in a closed area or delete it",
            "Room \"Den\": not enclosed: close its walls or room separation lines, or delete it",
            "Room \"Hall\": its placement couldn't be read",
            "Room \"Study\": redundant (another room is in the same area): delete one",
        ], list.RoomBlockers);
        Assert.StartsWith("4 Rooms are unplaced", list.Summary[0]);
        Assert.StartsWith("Room \"Bedroom 3\": not placed", MarkingList.Text(list));
        Assert.Equal(MarkingListResult.NotAllMarked, list.Headline);
    }

    // review round 2, findings 1 and 2: a model whose only Room is a blocker says so once, in the singular, and
    // names Revit's default "Room 100" once
    [Fact]
    public void Only_a_blocker_room_one_line_singular_and_the_name_once()
    {
        var list = MarkingList.Build(Model(Room("r", "Room", null, "100") with { Placement = RoomPlacement.NotEnclosed }));
        Assert.StartsWith("1 Room is unplaced, not enclosed or redundant", list.Summary[0]);
        Assert.DoesNotContain(list.Summary, l => l.StartsWith(MarkingListResult.NoRooms, StringComparison.Ordinal));
        Assert.Equal(["Room \"Room 100\": not enclosed: close its walls or room separation lines, or delete it"], list.RoomBlockers);
        Assert.DoesNotContain("Room Room", MarkingList.Text(list));
        Assert.Equal("A room with no name or number: not placed: place it in a closed area or delete it",
                     MarkingList.Build(Model(Room("x", null, null) with { Placement = RoomPlacement.Unplaced })).RoomBlockers.Single());
        Assert.Null(MarkReading.Rooms(Model(Room("r", "Room", null, "100") with { Placement = RoomPlacement.NotEnclosed })));
    }

    // review round 1, finding 3: "every room, window and door is marked" only when there are rooms and all are marked
    [Fact]
    public void The_headline_says_all_marked_only_when_rooms_are_drawn_and_marked()
    {
        Assert.Equal(MarkingListResult.NothingDrawn, MarkingList.Build(Model()).Headline);
        Assert.Equal(MarkingListResult.NoRooms, MarkingList.Build(Model(Window("w", true, "Casement"))).Headline);
        Assert.Equal(MarkingListResult.NotAllMarked, MarkingList.Build(Model(Room("r", "Bed", null))).Headline);
        Assert.Equal(MarkingListResult.AllMarked,
                     MarkingList.Build(Model(Room("r", "Bed", true), Window("w", true, "Casement"))).Headline);
    }

    // ---- the marking list -------------------------------------------------------------------------------------

    [Fact]
    public void The_list_puts_anything_unset_first_and_says_what_it_leaves_not_read()
    {
        var model = Model(Room("living", "Living", false, "101"), Room("bed", "Bedroom 2", null, "102"),
                          Window("w1", true, "Casement"), Window("w2", false, null),
                          Door("d1", false, true, "Side-hinged door"), Door("d2", null, false, "Sliding door"));
        var list = MarkingList.Build(model);
        Assert.Equal(["bed", "w2", "d2", "living", "w1", "d1"], list.Rows.Select(r => r.Id));
        Assert.Equal(["Bedroom 2 102", "Casement: 36 x 48"], list.Rows.Take(2).Select(r => r.Label));
        Assert.Equal(
        [
            "Gordium: Sleeping room: 1 of 2 rooms not marked, so no room is read for egress until each says Yes or No.",
            "Gordium: Escape opening: 1 of 4 windows and doors not marked, so no escape opening is read until each says Yes or No.",
            "Gordium: Exit door: all 2 doors marked.",
            "Gordium: Operation: 1 windows and doors have no operation Gordium reads, so their egress measures need review.",
            "Gordium: These are all the stairs: not set on Project Information, so no stair is read for egress until it says Yes.",
            "Gordium: These are all the guards and handrails: not set on Project Information, so no guard or handrail is read for egress until it says Yes.",
        ], list.Summary);
        var ticked = model with
        {
            ProjectMarks = new Dictionary<Guid, MarkValue> { [Marks.AllStairs.Guid] = new(true, 1), [Marks.AllGuards.Guid] = new(true, 1) },
        };
        Assert.Equal("Gordium: These are all the stairs: Yes (on Project Information).", MarkingList.Build(ticked).Summary[^2]);
        Assert.Equal("Gordium: These are all the guards and handrails: Yes (on Project Information).", MarkingList.Build(ticked).Summary[^1]);
        var unset = model with
        {
            ProjectMarks = new Dictionary<Guid, MarkValue> { [Marks.AllStairs.Guid] = new(false, 0), [Marks.AllGuards.Guid] = new(false, 0) },   // never set reads 0
        };
        Assert.Contains("not set on Project Information", MarkingList.Build(unset).Summary[^2]);
        Assert.Contains("not set on Project Information", MarkingList.Build(unset).Summary[^1]);
        var text = MarkingList.Text(list);
        Assert.StartsWith("Gordium: Sleeping room: 1 of 2", text);
        Assert.Contains("TO MARK  Room: Bedroom 2 102\n    Gordium: Sleeping room: not set - suggested: Yes", text);
    }

    [Fact]
    public void A_suggestion_is_only_ever_yes_and_only_on_an_unset_room()
    {
        var list = MarkingList.Build(Model(Room("a", "Master bedroom", false), Room("b", "Sleeping porch", null),
                                           Room("c", "Bedroom closet", true), Room("d", "Bath", null), Room("e", null, null)));
        var byId = list.Rows.ToDictionary(r => r.Id, r => r.Cells.Single(c => c.Mark == Marks.SleepingRoom));
        Assert.Null(byId["a"].Suggestion);                // marked No: the architect's own fact stands
        Assert.NotNull(byId["b"].Suggestion);
        Assert.Null(byId["c"].Suggestion);
        Assert.Null(byId["d"].Suggestion);                 // never a suggested No
        Assert.Null(byId["e"].Suggestion);
        Assert.Equal("(a room with no name or number)", list.Rows.Single(r => r.Id == "e").Label);
    }

    [Fact]
    public void An_operation_word_gordium_doesnt_read_is_listed_with_why()
    {
        var list = MarkingList.Build(Model(Door("d", false, true, "Casement"), Window("w", false, "Double-hung")));
        var door = list.Rows.Single(r => r.Id == "d").Cells.Single(c => c.Mark == Marks.Operation);
        Assert.Equal(MarkState.NotUnderstood, door.State);
        Assert.Contains("a window's operation, not a door's", door.Words);
        var window = list.Rows.Single(r => r.Id == "w").Cells.Single(c => c.Mark == Marks.Operation);
        Assert.Equal(MarkState.NotUnderstood, window.State);
        Assert.Contains("isn't one of Gordium's operations", window.Words);
        Assert.All(list.Rows, r => Assert.True(r.NeedsMarking));
    }

    [Fact]
    public void A_model_with_no_rooms_says_so()
    {
        var list = MarkingList.Build(Model(Window("w", true, "Casement")));
        Assert.Equal("No rooms are drawn: egress waits until the house's Rooms are placed.", list.Summary[0]);
    }
}
