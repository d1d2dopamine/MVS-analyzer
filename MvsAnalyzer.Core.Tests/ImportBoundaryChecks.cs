using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using MvsAnalyzer;

// Independent boundary checks: expected observations and counts are literal fixtures;
// digests are computed from the bytes written, never from the importer's decoded text.
internal static class ImportBoundaryChecks
{
    public static IEnumerable<(string Name, Action Run)> All => new (string, Action)[]
    {
        ("Import hashes exact encoded bytes and newline forms", RawByteDigests),
        ("Import owns metadata across failures and interleaved calls", ResultIsolation),
        ("Import sequence fallback counts and filtering are explicit", SequenceAndFiltering),
        ("Import profile maps columns and decimal-comma values", ProfileMapping),
        ("Import preserves exact malformed and empty input errors", InvalidInputs),
        ("Import cancellation precedes file access", PreCancelled),
        ("CSV parser independently observes cancellation", ParserCancellation),
        ("Import snapshot survives source replacement and deletion", SourceSnapshot),
        ("Legacy Read and Import preserve stable observations and metadata", LegacyParity),
        ("Import result metadata is init-only", MetadataShape)
    };

    private const string Plain = "entity,group,value,sequence\na,A,12,7\nb,B,24,9\n";
    private const string CleanSummary = "Rows read: 2; kept: 2; malformed: 0; invalid/nonfinite: 0; outside limits: 0; missing IDs: 0; sequence fallbacks: 0.";
    private static readonly Observation[] Expected =
    {
        new("a", "A", 12, 7, "value", ""), new("b", "B", 24, 9, "value", "")
    };

    private static void RawByteDigests() => Isolated(dir =>
    {
        var fixtures = new (string Name, byte[] Bytes, string Encoding)[]
        {
            ("utf8-lf", Encoding.UTF8.GetBytes(Plain), "utf-8"),
            ("utf8-crlf", Encoding.UTF8.GetBytes(Plain.Replace("\n", "\r\n")), "utf-8"),
            ("utf8-no-final-newline", Encoding.UTF8.GetBytes(Plain.TrimEnd('\n')), "utf-8"),
            ("utf8-bom", new byte[] { 239, 187, 191 }.Concat(Encoding.UTF8.GetBytes(Plain)).ToArray(), "utf-8-bom"),
            ("utf16le-bom", new byte[] { 255, 254 }.Concat(Encoding.Unicode.GetBytes(Plain)).ToArray(), "utf-16le-bom"),
            ("utf16be-bom", new byte[] { 254, 255 }.Concat(Encoding.BigEndianUnicode.GetBytes(Plain)).ToArray(), "utf-16be-bom"),
            ("utf16le", Encoding.Unicode.GetBytes(Plain), "utf-16le"),
            ("utf16be", Encoding.BigEndianUnicode.GetBytes(Plain), "utf-16be")
        };
        var digests = new HashSet<string>();
        foreach (var fixture in fixtures)
        {
            var result = CsvImporter.Import(Write(dir, fixture.Name, fixture.Bytes), 0, 100);
            Check(result, Expected, CleanSummary, fixture.Encoding, true, fixture.Bytes);
            Assert(digests.Add(result.SourceSha256), "Distinct raw encodings/newlines were conflated: " + fixture.Name);
        }
        // Literal CP1251 bytes for контроль, avoiding any registered code-page dependency.
        byte[] cyrillic = { 234, 238, 237, 242, 240, 238, 235, 252 };
        byte[] cp1251 = Encoding.ASCII.GetBytes("entity,group,value,sequence\n").Concat(cyrillic)
            .Concat(Encoding.ASCII.GetBytes(",A,12,7\nb,B,24,9\n")).ToArray();
        var legacy = CsvImporter.Import(Write(dir, "cp1251", cp1251), 0, 100);
        Check(legacy, new[] { new Observation("\u043a\u043e\u043d\u0442\u0440\u043e\u043b\u044c", "A", 12, 7, "value", ""), Expected[1] }, CleanSummary, "windows-1251", true, cp1251);
    });

    private static void ResultIsolation() => Isolated(dir =>
    {
        string seed = Write(dir, "legacy", Encoding.Unicode.GetPreamble().Concat(Encoding.Unicode.GetBytes(Plain)).ToArray());
        CsvImporter.Read(seed, 0, 100);
        var legacy = LegacyMetadata();
        byte[] firstBytes = Encoding.UTF8.GetBytes(Plain);
        string firstPath = Write(dir, "first", firstBytes);
        var first = CsvImporter.Import(firstPath, 0, 100);
        string otherPath = Write(dir, "other", Encoding.UTF8.GetBytes("entity;group;value\nx;C;31\ny;D;42\n"));
        var second = CsvImporter.Import(otherPath, 0, 100);
        Assert(!second.SequenceWasProvided && second.Observations[0] == new Observation("x", "C", 31, 1, "value", ""), "Second import fixture was not parsed independently.");
        Expect<InvalidDataException>(() => CsvImporter.Import(Write(dir, "bad", Encoding.UTF8.GetBytes("entity,group,value\na,A,NaN\n")), 0, 100),
            "No valid measurements. Rows read: 1; kept: 0; malformed: 0; invalid/nonfinite: 1; outside limits: 0; missing IDs: 0; sequence fallbacks: 0.");
        // Calls overlap safely without depending on a particular thread ordering.
        Parallel.For(0, 12, i =>
        {
            var result = CsvImporter.Import(i % 2 == 0 ? firstPath : otherPath, 0, 100);
            Assert(result.SequenceWasProvided == (i % 2 == 0), "Concurrent import metadata leaked between requests.");
            Assert(result.Observations[0].Value == (i % 2 == 0 ? 12 : 31), "Concurrent observations leaked.");
        });
        Check(first, Expected, CleanSummary, "utf-8", true, firstBytes);
        Assert(LegacyMetadata() == legacy, "Pure imports (including failure) changed legacy Last* metadata.");
        second.Observations.Clear();
        Check(first, Expected, CleanSummary, "utf-8", true, firstBytes);
    });

    private static void SequenceAndFiltering() => Isolated(dir =>
    {
        byte[] bytes = Encoding.UTF8.GetBytes("entity,group,value,sequence,variable,unit\na,A,12,8,value,ms\na,A,13,bad,value,ms\nb,B,24,5,value,ms\na,A,14\nb,B,NaN,bad\na,A,101,bad\n,A,12,2\nshort\n");
        var result = CsvImporter.Import(Write(dir, "filtered", bytes), 0, 100);
        Check(result, new[]
        {
            new Observation("a", "A", 12, 8, "value", "ms"), new Observation("a", "A", 13, 2, "value", "ms"),
            new Observation("b", "B", 24, 5, "value", "ms"), new Observation("a", "A", 14, 3, "value", "")
        }, "Rows read: 8; kept: 4; malformed: 1; invalid/nonfinite: 1; outside limits: 1; missing IDs: 1; sequence fallbacks: 2.", "utf-8", false, bytes);
        byte[] absent = Encoding.UTF8.GetBytes("entity,group,value\na,A,12\na,A,13\nb,B,24\n");
        var inferred = CsvImporter.Import(Write(dir, "absent-sequence", absent), 0, 100);
        Check(inferred, new[] { new Observation("a", "A", 12, 1, "value", ""), new Observation("a", "A", 13, 2, "value", ""), new Observation("b", "B", 24, 1, "value", "") },
            "Rows read: 3; kept: 3; malformed: 0; invalid/nonfinite: 0; outside limits: 0; missing IDs: 0; sequence fallbacks: 0.", "utf-8", false, absent);
    });

    private static void ProfileMapping() => Isolated(dir =>
    {
        var profile = new ImportProfile("test", "Test", "boundary-test", '|', true, new()
        {
            ["entity"] = new[] { "person" }, ["group"] = new[] { "cohort" }, ["value"] = new[] { "amount" },
            ["sequence"] = new[] { "ordinal" }, ["variable"] = new[] { "outcome" }, ["unit"] = new[] { "scale" }
        });
        byte[] bytes = Encoding.UTF8.GetBytes("person|cohort|amount|ordinal|outcome|scale\n\"a|quoted\"|A|1.234,50|11|duration|ms\nb|B|2,25|12|duration|ms\n");
        var result = CsvImporter.Import(Write(dir, "profile", bytes), 0, 2000, profile);
        Check(result, new[] { new Observation("a|quoted", "A", 1234.5, 11, "duration", "ms"), new Observation("b", "B", 2.25, 12, "duration", "ms") }, CleanSummary, "utf-8", true, bytes);
    });

    private static void InvalidInputs() => Isolated(dir =>
    {
        var cases = new (string Text, string Error)[]
        {
            ("", "The file does not contain data rows."),
            ("entity,group,value\n", "The file does not contain data rows."),
            ("entity,group,other\na,A,12\nb,B,24\n", "Required columns: entity, group/condition, value."),
            ("entity,group,value\n\"a,A,12\n", "Unterminated quoted CSV field."),
            ("entity,group,value\na,A,12\n", "Use 2–10 independent groups."),
            ("entity,group,value,variable\na,A,12,x\nb,B,24,y\n", "Use one outcome variable per run."),
            ("entity,group,value\na,A,NaN\nb,B,Infinity\nc,A,101\n,A,12\nshort\n", "No valid measurements. Rows read: 5; kept: 0; malformed: 1; invalid/nonfinite: 2; outside limits: 1; missing IDs: 1; sequence fallbacks: 0.")
        };
        for (int i = 0; i < cases.Length; i++)
        {
            var c = cases[i]; string path = Write(dir, "invalid" + i, Encoding.UTF8.GetBytes(c.Text));
            var before = LegacyMetadata();
            Expect<InvalidDataException>(() => CsvImporter.Import(path, 0, 100), c.Error);
            Assert(LegacyMetadata() == before, "A failing import published legacy metadata.");
        }
        Expect<ArgumentException>(() => CsvImporter.Import(Path.Combine(dir, "missing"), 4, 4), "Invalid input bounds.");
        string single = Write(dir, "single", Encoding.UTF8.GetBytes("entity,group,value\na,A,12\n"));
        var accepted = CsvImporter.Import(single, 0, 100, allowSingleGroup: true);
        Assert(accepted.Observations.SequenceEqual(new[] { new Observation("a", "A", 12, 1, "value", "") }) && !accepted.SequenceWasProvided, "Single-group opt-in changed observations.");
        string eleven = Write(dir, "eleven", Encoding.UTF8.GetBytes("entity,group,value\n" + string.Join("\n", Enumerable.Range(0, 11).Select(i => $"e{i},G{i},12"))));
        Expect<InvalidDataException>(() => CsvImporter.Import(eleven, 0, 100), "Use 2–10 independent groups.");
        Expect<InvalidDataException>(() => CsvImporter.Import(eleven, 0, 100, allowSingleGroup: true), "Use 1–10 conditions.");
    });

    private static void PreCancelled() => Isolated(dir =>
    {
        using var stop = new CancellationTokenSource(); stop.Cancel();
        var before = LegacyMetadata();
        try { CsvImporter.Import(Path.Combine(dir, "does-not-exist.csv"), 0, 100, cancellationToken: stop.Token); }
        catch (OperationCanceledException ex)
        {
            Assert(ex.CancellationToken == stop.Token, "Cancellation lost the caller's token.");
            Assert(LegacyMetadata() == before, "Cancellation changed legacy metadata.");
            return;
        }
        throw new Exception("A pre-cancelled import did not stop before file access.");
    });

    private static void ParserCancellation()
    {
        // Exercise the parser directly, rather than relying on a CancelAfter race or
        // merely proving Import's entry guard. This makes no I/O interruption claim.
        MethodInfo parse = typeof(CsvImporter).GetMethod("Parse", BindingFlags.NonPublic | BindingFlags.Static,
            null, new[] { typeof(string), typeof(char), typeof(CancellationToken) }, null)
            ?? throw new Exception("Missing cancellable parser boundary.");
        using var stop = new CancellationTokenSource(); stop.Cancel();
        var before = LegacyMetadata();
        try { parse.Invoke(null, new object[] { Plain, char.MinValue, stop.Token }); }
        catch (TargetInvocationException ex) when (ex.InnerException is OperationCanceledException cancelled)
        {
            Assert(cancelled.CancellationToken == stop.Token, "Parser cancellation lost the caller token.");
            Assert(LegacyMetadata() == before, "Parser cancellation published legacy metadata.");
            return;
        }
        throw new Exception("The parser ignored cancellation at its own boundary.");
    }

    private static void SourceSnapshot() => Isolated(dir =>
    {
        byte[] bytes = Encoding.UTF8.GetBytes(Plain); string path = Write(dir, "source", bytes);
        var result = CsvImporter.Import(path, 0, 100);
        File.WriteAllText(path, "entity,group,value\nx,C,99\ny,D,98\n", new UTF8Encoding(false));
        Assert(Hash(File.ReadAllBytes(path)) != result.SourceSha256, "Replacement fixture was not distinct.");
        Check(result, Expected, CleanSummary, "utf-8", true, bytes);
        File.Delete(path);
        Check(result, Expected, CleanSummary, "utf-8", true, bytes);
    });

    private static void LegacyParity() => Isolated(dir =>
    {
        byte[] bytes = new byte[] { 239, 187, 191 }.Concat(Encoding.UTF8.GetBytes(Plain)).ToArray();
        string path = Write(dir, "parity", bytes);
        var imported = CsvImporter.Import(path, 0, 100); var read = CsvImporter.Read(path, 0, 100);
        Check(imported, Expected, CleanSummary, "utf-8-bom", true, bytes);
        Assert(read.SequenceEqual(Expected) && read.SequenceEqual(imported.Observations), "Read differs from expected observations or Import.");
        Assert(LegacyMetadata() == (CleanSummary, "utf-8-bom", true), "Read did not publish matching metadata.");
        read.Clear();
        Assert(imported.Observations.SequenceEqual(Expected), "Independent calls shared a mutable observation list.");
    });

    private static void MetadataShape()
    {
        Type type = typeof(CsvImportResult);
        Assert(type.IsSealed, "Import result must be sealed.");
        foreach (string name in new[] { "Summary", "EncodingName", "SequenceWasProvided", "SourceSha256" })
        {
            PropertyInfo property = type.GetProperty(name)!;
            Assert(property != null && property.CanRead, "Missing metadata property: " + name);
            MethodInfo? setter = property!.SetMethod;
            Assert(setter == null || setter.ReturnParameter.GetRequiredCustomModifiers().Contains(typeof(System.Runtime.CompilerServices.IsExternalInit)), "Metadata is writable after initialization: " + name);
        }
        Assert(type.GetProperty("Observations")!.PropertyType == typeof(List<Observation>), "The result's caller-owned list contract changed.");
    }

    private static void Check(CsvImportResult result, IEnumerable<Observation> observations, string summary, string encoding, bool sequence, byte[] bytes)
    {
        Assert(result.Observations.SequenceEqual(observations), "Observations differ from independent fixture.");
        Assert(result.Summary == summary, "Summary differs: " + result.Summary);
        Assert(result.EncodingName == encoding, "Unexpected encoding: " + result.EncodingName);
        Assert(result.SequenceWasProvided == sequence, "Sequence provenance differs.");
        Assert(result.SourceSha256 == Hash(bytes), "Digest does not match the exact source bytes.");
    }
    private static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    private static (string, string, bool) LegacyMetadata() => (CsvImporter.LastImportSummary, CsvImporter.LastEncodingName, CsvImporter.LastSequenceWasProvided);
    private static string Write(string dir, string name, byte[] bytes) { string path = Path.Combine(dir, name + ".csv"); File.WriteAllBytes(path, bytes); return path; }
    private static void Expect<T>(Action action, string message) where T : Exception
    {
        try { action(); } catch (T ex) { Assert(ex.Message == message, $"Expected '{message}', got '{ex.Message}'."); return; }
        throw new Exception("Expected " + typeof(T).Name + ": " + message);
    }
    private static void Assert(bool condition, string message) { if (!condition) throw new Exception(message); }
    private static void Isolated(Action<string> action)
    {
        string dir = Path.Combine(Path.GetTempPath(), "mvs-import-boundary-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir); try { action(dir); } finally { Directory.Delete(dir, true); }
    }
}
