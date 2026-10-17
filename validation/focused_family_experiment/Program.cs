using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace MvsAnalyzer.FocusedFamilyExperiment;

// Isolated development diagnostic, never a production policy or scientific GO.
// Input has no condition/scenario selector. Every case receives every fixed family.
internal static class Program
{
    private const string InputSchema = "mvs-focused-family-input/v1";
    private const string OutputSchema = "mvs-focused-family-diagnostic/v1";
    private const double Alpha = .05;
    private const int MaximumCases = 6000;
    private const int MaximumInputBytes = 8 * 1024 * 1024;
    private const int PartitionFamilyCount = 4;
    private static readonly JsonSerializerOptions Json = new() { PropertyNamingPolicy = JsonNamingPolicy.CamelCase };
    private static readonly string[] FrozenLegacyKeys =
    {
        "median", "standard_deviation", "coefficient_of_variation", "mad", "iqr", "normalized_mad",
        "normalized_iqr", "mean", "rms", "range", "geometric_mean", "trimmed_mean_20"
    };
    private static readonly FamilyDefinition[] Families =
    {
        new("all12", new[] { 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 }),
        new("location4", new[] { 0, 7, 10, 11 }),
        new("variability7", new[] { 1, 2, 3, 4, 5, 6, 9 }),
        new("absolute4", new[] { 1, 3, 4, 9 }),
        new("relative3", new[] { 2, 5, 6 }),
        new("magnitude1", new[] { 8 })
    };
    private static readonly string[] PartitionNames = { "location4", "absolute4", "relative3", "magnitude1" };

    private sealed record FamilyDefinition(string Name, int[] MemberIndices)
    {
        public string[] MemberNames => MemberIndices.Select(i => FrozenLegacyKeys[i]).ToArray();
        public int FullDenominator => MemberIndices.Length;
    }

    private sealed record InputCase(string Id, double?[] PValues, bool[] Available);
    private sealed record MemberResult(int Index, string Name, bool Available, double? RawP, double? AdjustedP, bool Rejected);
    private sealed record FamilyResult(double? MinAdjustedP, bool AnyRejected, int AvailableCount, int FullDenominator,
        int Multiplier, MemberResult[] Members, string[] RejectedMembers);
    private sealed record PartitionResult(int FamilyCount, Dictionary<string, FamilyResult> Families, bool AnyRejected,
        double? MinAdjustedP, string[] RejectedMembers);
    private sealed record NaiveUnionResult(string Interpretation, bool AnyRejected, string[] RejectedFamilies, string[] RejectedMembers);
    private sealed record CaseResult(string Id, string AvailabilityStatus, Dictionary<string, FamilyResult> Families,
        PartitionResult SimultaneousPartition, NaiveUnionResult NaiveFocusedUnion);

    public static int Main(string[] args)
    {
        try
        {
            VerifyRegistryAndPartition();
            object result;
            if (args.Length == 1 && args[0] == "--self-test")
            {
                result = SelfTest();
            }
            else if (args.Length == 2 && args[0] == "--input")
            {
                using Stream input = args[1] == "-" ? Console.OpenStandardInput() : File.OpenRead(args[1]);
                byte[] bytes = ReadBounded(input);
                InputCase[] cases = ParseInput(bytes);
                result = new
                {
                    schemaVersion = OutputSchema,
                    status = "isolated-development-diagnostic",
                    decisionStatus = "no-go",
                    alpha = Alpha,
                    registryKeys = FrozenLegacyKeys,
                    provenance = new
                    {
                        harnessSha256 = Hash(File.ReadAllBytes(Assembly.GetExecutingAssembly().Location)),
                        coreSha256 = Hash(File.ReadAllBytes(typeof(MetricRegistry).Assembly.Location)),
                        inputSha256 = Hash(bytes)
                    },
                    familyDefinitions = Families,
                    cases = cases.Select(Evaluate).ToArray()
                };
            }
            else
            {
                throw new ArgumentException("Usage: --input FILE | --input - | --self-test");
            }

            // Complete validation and serialization before emitting any success output.
            Console.Out.WriteLine(JsonSerializer.Serialize(result, Json));
            return 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error.ToString());
            return 1;
        }
    }

    private static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();

    private static void VerifyRegistryAndPartition()
    {
        if (!MetricRegistry.LegacyKeys.SequenceEqual(FrozenLegacyKeys, StringComparer.Ordinal))
            throw new InvalidOperationException("The exact frozen twelve-metric LegacyKeys literal does not match Core.");
        if (Families.Length != 6 || Families.Select(f => f.Name).Distinct(StringComparer.Ordinal).Count() != 6)
            throw new InvalidOperationException("The fixed family registry is malformed.");
        foreach (FamilyDefinition family in Families)
        {
            if (family.MemberIndices.Length == 0 || family.MemberIndices.Any(i => i < 0 || i >= FrozenLegacyKeys.Length)
                || family.MemberIndices.Distinct().Count() != family.MemberIndices.Length)
                throw new InvalidOperationException("Invalid fixed family membership: " + family.Name);
        }
        int[] partition = PartitionNames.SelectMany(name => Families.Single(f => f.Name == name).MemberIndices).ToArray();
        if (PartitionNames.Length != PartitionFamilyCount || partition.Length != FrozenLegacyKeys.Length
            || !partition.OrderBy(i => i).SequenceEqual(Enumerable.Range(0, FrozenLegacyKeys.Length)))
            throw new InvalidOperationException("The simultaneous partition must be disjoint and cover all twelve metrics.");
    }

    private static byte[] ReadBounded(Stream input)
    {
        using var buffer = new MemoryStream();
        var chunk = new byte[8192];
        while (true)
        {
            // Read at most one byte beyond the cap; never buffer an unbounded input.
            int count = input.Read(chunk, 0, Math.Min(chunk.Length, MaximumInputBytes + 1 - checked((int)buffer.Length)));
            if (count == 0) return buffer.ToArray();
            if (buffer.Length + count > MaximumInputBytes)
                throw new InvalidDataException("Input exceeds the 8 MiB byte limit.");
            buffer.Write(chunk, 0, count);
        }
    }

    private static InputCase[] ParseInput(byte[] bytes)
    {
        if (bytes.Length > MaximumInputBytes) throw new InvalidDataException("Input exceeds the 8 MiB byte limit.");
        using JsonDocument document = JsonDocument.Parse(bytes, new JsonDocumentOptions
        {
            AllowTrailingCommas = false,
            CommentHandling = JsonCommentHandling.Disallow,
            MaxDepth = 32
        });
        JsonElement root = document.RootElement;
        RequireKeys(root, "input", "schemaVersion", "cases");
        JsonElement schema = root.GetProperty("schemaVersion");
        if (schema.ValueKind != JsonValueKind.String || schema.GetString() != InputSchema)
            throw new InvalidDataException("Unsupported or missing input schemaVersion.");
        JsonElement cases = root.GetProperty("cases");
        if (cases.ValueKind != JsonValueKind.Array) throw new InvalidDataException("cases must be an array.");
        if (cases.GetArrayLength() > MaximumCases) throw new InvalidDataException("Input exceeds the 6000 case limit.");
        var parsed = new List<InputCase>(cases.GetArrayLength());
        var ids = new HashSet<string>(StringComparer.Ordinal);
        foreach (JsonElement item in cases.EnumerateArray())
        {
            RequireKeys(item, "case", "id", "pValues", "available");
            JsonElement idValue = item.GetProperty("id");
            if (idValue.ValueKind != JsonValueKind.String) throw new InvalidDataException("Each case id must be a string.");
            string id = idValue.GetString()!;
            if (!ids.Add(id)) throw new InvalidDataException("Duplicate case id: " + id);
            JsonElement pValues = item.GetProperty("pValues"), available = item.GetProperty("available");
            RequireVector(pValues, "pValues");
            RequireVector(available, "available");
            var p = new double?[FrozenLegacyKeys.Length];
            var mask = new bool[FrozenLegacyKeys.Length];
            for (int i = 0; i < FrozenLegacyKeys.Length; i++)
            {
                if (available[i].ValueKind != JsonValueKind.True && available[i].ValueKind != JsonValueKind.False)
                    throw new InvalidDataException("Availability entries must be JSON booleans.");
                mask[i] = available[i].GetBoolean();
                if (!mask[i])
                {
                    if (pValues[i].ValueKind != JsonValueKind.Null)
                        throw new InvalidDataException("Unavailable metrics must have null p-values.");
                    continue;
                }
                if (pValues[i].ValueKind != JsonValueKind.Number || !pValues[i].TryGetDouble(out double value)
                    || !double.IsFinite(value) || value < 0 || value > 1)
                    throw new InvalidDataException("Available metrics require finite numeric p-values in [0,1].");
                p[i] = value;
            }
            parsed.Add(new InputCase(id, p, mask));
        }
        return parsed.ToArray();
    }

    private static void RequireKeys(JsonElement value, string context, params string[] expected)
    {
        if (value.ValueKind != JsonValueKind.Object) throw new InvalidDataException(context + " must be an object.");
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (JsonProperty property in value.EnumerateObject())
        {
            if (!seen.Add(property.Name)) throw new InvalidDataException("Duplicate " + context + " property: " + property.Name);
            if (!expected.Contains(property.Name, StringComparer.Ordinal))
                throw new InvalidDataException("Unknown " + context + " property: " + property.Name);
        }
        if (seen.Count != expected.Length) throw new InvalidDataException("Missing required " + context + " property.");
    }

    private static void RequireVector(JsonElement value, string name)
    {
        if (value.ValueKind != JsonValueKind.Array || value.GetArrayLength() != FrozenLegacyKeys.Length)
            throw new InvalidDataException(name + " must contain exactly twelve entries.");
    }

    private static FamilyResult EvaluateFamily(InputCase input, FamilyDefinition family, int familyCount = 1)
    {
        // The full denominator never shrinks when members are unavailable. The simultaneous
        // partition uses one multiplication by 4*m, avoiding sequential-rounding semantics.
        int multiplier = checked(family.FullDenominator * familyCount);
        MemberResult[] members = family.MemberIndices.Select(i =>
        {
            double? raw = input.PValues[i];
            double? adjusted = raw.HasValue ? Math.Min(1, raw.Value * multiplier) : null;
            bool rejected = raw.HasValue && DecisionPolicy.Reject(raw.Value, Alpha, multiplier);
            return new MemberResult(i, FrozenLegacyKeys[i], input.Available[i], raw, adjusted, rejected);
        }).ToArray();
        double? minimum = members.Where(m => m.Available).Select(m => m.AdjustedP).DefaultIfEmpty(null).Min();
        string[] rejectedMembers = members.Where(m => m.Rejected).Select(m => m.Name).ToArray();
        return new FamilyResult(minimum, rejectedMembers.Length != 0, members.Count(m => m.Available),
            family.FullDenominator, multiplier, members, rejectedMembers);
    }

    private static CaseResult Evaluate(InputCase input)
    {
        Dictionary<string, FamilyResult> families = Families.ToDictionary(f => f.Name, f => EvaluateFamily(input, f), StringComparer.Ordinal);
        Dictionary<string, FamilyResult> partition = PartitionNames.ToDictionary(name => name,
            name => EvaluateFamily(input, Families.Single(f => f.Name == name), PartitionFamilyCount), StringComparer.Ordinal);
        string[] partitionRejected = OrderedRejectedMembers(partition.Values);
        var simultaneous = new PartitionResult(PartitionFamilyCount, partition, partitionRejected.Length != 0,
            partition.Values.Select(f => f.MinAdjustedP).DefaultIfEmpty(null).Min(), partitionRejected);
        FamilyDefinition[] focused = PartitionNames.Select(name => Families.Single(f => f.Name == name)).ToArray();
        string[] focusedRejected = focused.Where(f => families[f.Name].AnyRejected).Select(f => f.Name).ToArray();
        var naive = new NaiveUnionResult("diagnostic-only-not-globally-controlled", focusedRejected.Length != 0,
            focusedRejected, OrderedRejectedMembers(focused.Select(f => families[f.Name])));
        int availableCount = input.Available.Count(value => value);
        string availabilityStatus = availableCount == 0 ? "all-unavailable" :
            availableCount == FrozenLegacyKeys.Length ? "all-available" : "partially-available";
        return new CaseResult(input.Id, availabilityStatus, families, simultaneous, naive);
    }

    private static string[] OrderedRejectedMembers(IEnumerable<FamilyResult> families)
    {
        var names = families.SelectMany(f => f.RejectedMembers).ToHashSet(StringComparer.Ordinal);
        return FrozenLegacyKeys.Where(names.Contains).ToArray();
    }

    private static object SelfTest()
    {
        var counts = new SortedDictionary<string, int>(StringComparer.Ordinal);
        void Check(string category, bool condition, string detail)
        {
            if (!condition) throw new InvalidOperationException("Self-test failed [" + category + "]: " + detail);
            counts[category] = counts.GetValueOrDefault(category) + 1;
        }
        void Invalid(string text, string detail)
        {
            bool rejected = false;
            try { _ = ParseInput(Encoding.UTF8.GetBytes(text)); }
            catch (Exception error) when (error is InvalidDataException or JsonException) { rejected = true; }
            Check("malformedInput", rejected, detail);
        }
        static string Envelope(string cases) => "{\"schemaVersion\":\"" + InputSchema + "\",\"cases\":[" + cases + "]}";
        static string CaseJson(string id, string p, string available) => "{\"id\":" + JsonSerializer.Serialize(id)
            + ",\"pValues\":[" + p + "],\"available\":[" + available + "]}";
        static string Repeat(string value, int count = 12) => string.Join(',', Enumerable.Repeat(value, count));
        static InputCase Synthetic(double? value, int? onlyIndex = null) => new("synthetic",
            Enumerable.Range(0, 12).Select(i => onlyIndex.HasValue && i != onlyIndex ? null : value).ToArray(),
            Enumerable.Range(0, 12).Select(i => value.HasValue && (!onlyIndex.HasValue || i == onlyIndex)).ToArray());

        Check("registryAndPartition", MetricRegistry.LegacyKeys.SequenceEqual(FrozenLegacyKeys), "exact legacy key order");
        Check("registryAndPartition", Families.Select(f => f.FullDenominator).SequenceEqual(new[] { 12, 4, 7, 4, 3, 1 }), "fixed sizes");
        int[] partitionIndices = PartitionNames.SelectMany(name => Families.Single(f => f.Name == name).MemberIndices).ToArray();
        Check("registryAndPartition", partitionIndices.Distinct().Count() == 12 && partitionIndices.Length == 12, "partition disjoint");
        Check("registryAndPartition", partitionIndices.Order().SequenceEqual(Enumerable.Range(0, 12)), "partition complete");

        foreach (int multiplier in new[] { 1, 3, 4, 7, 12, 16 })
        {
            double boundary = Alpha / multiplier;
            foreach ((double p, bool expected, string label) in new[]
            {
                (Math.BitDecrement(boundary), true, "immediate double below"),
                (boundary, false, "strict boundary"),
                (Math.BitIncrement(boundary), false, "immediate double above"),
                (0d, true, "zero"), (1d, false, "one")
            })
            {
                Check("strictBoundaries", DecisionPolicy.Reject(p, Alpha, multiplier) == expected, multiplier + ": " + label);
                FamilyDefinition family = multiplier == 16 ? Families.Single(f => f.Name == "absolute4")
                    : Families.First(f => f.FullDenominator == multiplier);
                FamilyResult native = EvaluateFamily(Synthetic(p), family, multiplier == 16 ? 4 : 1);
                Check("strictBoundaries", native.AnyRejected == expected && native.Members.All(m => m.Rejected == expected), "native " + multiplier + ": " + label);
                Check("strictBoundaries", native.MinAdjustedP == Math.Min(1, p * multiplier)
                    && native.Members.All(m => m.AdjustedP == Math.Min(1, p * multiplier)), "single multiplication " + multiplier + ": " + label);
            }
        }

        CaseResult missing = Evaluate(Synthetic(null));
        Check("availability", missing.AvailabilityStatus == "all-unavailable", "all-unavailable status");
        foreach (FamilyDefinition family in Families)
        {
            FamilyResult result = missing.Families[family.Name];
            Check("availability", result.MinAdjustedP is null && !result.AnyRejected && result.AvailableCount == 0
                && result.FullDenominator == family.FullDenominator && result.Multiplier == family.FullDenominator
                && result.Members.All(m => !m.Available && m.RawP is null && m.AdjustedP is null && !m.Rejected), "empty " + family.Name);
        }
        Check("availability", missing.SimultaneousPartition.MinAdjustedP is null && !missing.SimultaneousPartition.AnyRejected
            && !missing.NaiveFocusedUnion.AnyRejected, "empty unions");
        CaseResult partial = Evaluate(Synthetic(.003, 3));
        Check("availability", partial.AvailabilityStatus == "partially-available", "partial status");
        foreach (string name in new[] { "all12", "variability7", "absolute4" })
        {
            FamilyResult result = partial.Families[name];
            Check("availability", result.AvailableCount == 1 && result.MinAdjustedP == .003 * result.FullDenominator
                && result.RejectedMembers.SequenceEqual(new[] { "mad" }), "missing does not shrink " + name);
        }
        FamilyResult absolutePartition = partial.SimultaneousPartition.Families["absolute4"];
        Check("availability", absolutePartition.FullDenominator == 4 && absolutePartition.Multiplier == 16
            && absolutePartition.MinAdjustedP == .003 * 16 && absolutePartition.AnyRejected, "partition keeps full denominator");
        Check("availability", Evaluate(Synthetic(.5)).AvailabilityStatus == "all-available", "complete status");
        CaseResult naiveOnly = Evaluate(Synthetic(.02, 8));
        Check("unionSemantics", naiveOnly.NaiveFocusedUnion.AnyRejected && !naiveOnly.SimultaneousPartition.AnyRejected
            && !naiveOnly.Families["all12"].AnyRejected, "naive union can reject without simultaneous or all12 rejection");
        Check("unionSemantics", naiveOnly.NaiveFocusedUnion.Interpretation == "diagnostic-only-not-globally-controlled"
            && naiveOnly.NaiveFocusedUnion.RejectedMembers.SequenceEqual(new[] { "rms" }), "naive union labeled and identified");

        string validCase = CaseJson("a", Repeat("0.5"), Repeat("true"));
        Check("validInput", ParseInput(Encoding.UTF8.GetBytes(Envelope(validCase))).Length == 1, "one valid case");
        Check("validInput", ParseInput(Encoding.UTF8.GetBytes(Envelope(CaseJson("empty", Repeat("null"), Repeat("false"))))).Length == 1, "unavailable case");
        Check("validInput", ParseInput(Encoding.UTF8.GetBytes(Envelope(""))).Length == 0, "empty cases array");
        Invalid(Envelope(validCase + "," + validCase), "duplicate ids");
        Invalid(Envelope(validCase.Replace("\"pValues\":", "\"scenario\":\"location\",\"pValues\":")), "scenario selection rejected");
        Invalid(Envelope(validCase.Replace("\"pValues\":", "\"condition\":\"null\",\"pValues\":")), "condition selection rejected");
        Invalid(Envelope(validCase).Replace("\"cases\":", "\"extra\":0,\"cases\":"), "unknown root key");
        Invalid(Envelope(validCase).Replace(InputSchema, "mvs-focused-family-input/v2"), "unsupported schema");
        Invalid("{\"cases\":[]}", "missing schema");
        Invalid("{\"schemaVersion\":1,\"cases\":[]}", "schema type");
        Invalid(Envelope(validCase).Replace("\"cases\":", "\"cases\":[],\"cases\":"), "duplicate root key");
        Invalid(Envelope(validCase.Replace("\"id\":\"a\",", "\"id\":\"a\",\"id\":\"b\",")), "duplicate case key");
        Invalid(Envelope(validCase.Replace("\"id\":\"a\",", "")), "missing id");
        Invalid(Envelope(validCase.Replace("\"id\":\"a\"", "\"id\":null")), "null id");
        Invalid(Envelope(CaseJson("a", Repeat("0.5", 11), Repeat("true"))), "short p vector");
        Invalid(Envelope(CaseJson("a", Repeat("0.5", 13), Repeat("true"))), "long p vector");
        Invalid(Envelope(CaseJson("a", Repeat("0.5"), Repeat("true", 11))), "short availability vector");
        Invalid(Envelope(CaseJson("a", Repeat("0.5"), Repeat("true", 13))), "long availability vector");
        Invalid(Envelope(CaseJson("a", Repeat("0.5"), Repeat("1"))), "nonboolean availability");
        Invalid(Envelope(CaseJson("a", Repeat("null"), Repeat("true"))), "available with null p");
        Invalid(Envelope(CaseJson("a", Repeat("0.5"), Repeat("false"))), "unavailable with numeric p");
        foreach (string badP in new[] { "-0.01", "1.01", "1e400", "\"NaN\"", "\"0.1\"", "true" })
            Invalid(Envelope(CaseJson("a", Repeat(badP), Repeat("true"))), "invalid p value " + badP);
        Invalid("[]", "root must be object");
        Invalid(Envelope("null"), "case must be object");
        Invalid("{\"schemaVersion\":\"" + InputSchema + "\",\"cases\":null}", "cases must be array");
        Invalid(Envelope(validCase) + "garbage", "trailing garbage");
        Invalid(Envelope(validCase + ","), "trailing comma");
        Invalid("/*comment*/" + Envelope(validCase), "comments rejected");
        string maximumCases = string.Join(',', Enumerable.Range(0, MaximumCases).Select(i => CaseJson(i.ToString(), Repeat("null"), Repeat("false"))));
        Check("limits", ParseInput(Encoding.UTF8.GetBytes(Envelope(maximumCases))).Length == MaximumCases, "6000 cases accepted");
        Invalid(Envelope(maximumCases + "," + CaseJson("excess", Repeat("null"), Repeat("false"))), "6001 cases rejected");
        byte[] cap = Enumerable.Repeat((byte)' ', MaximumInputBytes).ToArray();
        Encoding.UTF8.GetBytes(Envelope("")).CopyTo(cap, 0);
        using (var atCap = new MemoryStream(cap, writable: false))
            Check("limits", ParseInput(ReadBounded(atCap)).Length == 0, "exactly 8 MiB accepted");
        bool exceeded = false;
        using (var overCap = new MemoryStream(new byte[MaximumInputBytes + 1], writable: false))
        {
            try { _ = ReadBounded(overCap); }
            catch (InvalidDataException) { exceeded = true; }
        }
        Check("limits", exceeded, "over 8 MiB rejected while reading");

        // Actual Core computations on a fixed measurement vector, not precomputed metrics
        // or a new scientific sample. These checks pin interpretation and units only.
        double[] measurements = { 1, 2, 4, 8, 16, 32, 64, 128 };
        double[] original = MetricRegistry.ComputeLegacy(measurements);
        double[] shifted = MetricRegistry.ComputeLegacy(measurements.Select(x => x + 100).ToArray());
        double[] scaled = MetricRegistry.ComputeLegacy(measurements.Select(x => 2 * x).ToArray());
        Check("measurementTransformations", original.Length == 12 && shifted.Length == 12 && scaled.Length == 12
            && original.Concat(shifted).Concat(scaled).All(double.IsFinite), "actual Core vectors finite and ordered");
        foreach (int index in new[] { 1, 3, 4, 9 })
            Check("measurementTransformations", NearlyEqual(shifted[index], original[index]), "absolute translation invariance: " + FrozenLegacyKeys[index]);
        foreach (int index in new[] { 2, 5, 6 })
            Check("measurementTransformations", !NearlyEqual(shifted[index], original[index]), "relative translation change: " + FrozenLegacyKeys[index]);
        foreach (int index in new[] { 0, 7, 11 })
            Check("measurementTransformations", NearlyEqual(shifted[index], original[index] + 100), "location shift by 100: " + FrozenLegacyKeys[index]);
        Check("measurementTransformations", !NearlyEqual(shifted[10], original[10] + 100), "geometric mean is not translation equivariant");
        foreach (int index in new[] { 0, 1, 3, 4, 7, 8, 9, 10, 11 })
            Check("measurementTransformations", NearlyEqual(scaled[index], 2 * original[index]), "absolute/location scaling by two: " + FrozenLegacyKeys[index]);
        foreach (int index in new[] { 2, 5, 6 })
            Check("measurementTransformations", NearlyEqual(scaled[index], original[index]), "relative positive-scale invariance: " + FrozenLegacyKeys[index]);

        return new
        {
            schemaVersion = "mvs-focused-family-self-test/v1",
            status = "passed",
            decisionStatus = "no-go",
            totalChecks = counts.Values.Sum(),
            checksByCategory = counts,
            measurementFixture = new
            {
                measurements,
                shift = 100,
                scale = 2,
                relativeTolerance = 1e-12,
                original = FrozenLegacyKeys.Select((key, i) => (key, value: original[i])).ToDictionary(item => item.key, item => item.value),
                shifted = FrozenLegacyKeys.Select((key, i) => (key, value: shifted[i])).ToDictionary(item => item.key, item => item.value),
                scaled = FrozenLegacyKeys.Select((key, i) => (key, value: scaled[i])).ToDictionary(item => item.key, item => item.value)
            }
        };
    }

    private static bool NearlyEqual(double actual, double expected) => double.IsFinite(actual) && double.IsFinite(expected)
        && Math.Abs(actual - expected) <= 1e-12 * Math.Max(Math.Abs(actual), Math.Abs(expected));
}
