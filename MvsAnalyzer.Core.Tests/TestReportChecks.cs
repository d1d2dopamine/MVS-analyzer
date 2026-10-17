using System.Runtime.CompilerServices;

internal static class TestReportChecks
{
    internal static IEnumerable<(string Name, Action Run)> All => new (string, Action)[] {
        ("Failure report retains nested types and stack frames", Details),
        ("Failure report continues and preserves nonzero status", Continues),
        ("Successful test report preserves existing lines and status", Success),
        ("Empty test report preserves legacy summary", Empty),
        ("Failure report omits arbitrary exception data", NoData)
    };
    internal static int Fixture(TextWriter output) => TestReport.Run(new (string, Action)[] {
        ("controlled nested failure", ThrowOuter), ("following control", () => { })
    }, output);
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void ThrowInner() => throw new UnauthorizedAccessException("controlled inner fixture");
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void ThrowOuter()
    {
        try { ThrowInner(); }
        catch (UnauthorizedAccessException inner) { throw new IOException("controlled outer fixture", inner); }
    }
    private static void Require(bool value, string message) { if (!value) throw new Exception(message); }
    private static void Details()
    {
        using var output = new StringWriter();
        Require(Fixture(output) == 1, "Failure became success.");
        string text = output.ToString();
        foreach (string expected in new[] { "FAIL  controlled nested failure: controlled outer fixture", "DETAIL System.IO.IOException", "System.UnauthorizedAccessException", "controlled inner fixture", "ThrowInner", "ThrowOuter", "PASS  following control", "1/2 tests passed" })
            Require(text.Contains(expected, StringComparison.Ordinal), "Missing failure detail: " + expected);
    }
    private static void Continues()
    {
        int visited = 0; using var output = new StringWriter();
        int code = TestReport.Run(new (string, Action)[] { ("one", () => { visited++; throw new ArgumentException("one"); }), ("two", () => { visited++; throw new InvalidOperationException("two"); }), ("three", () => visited++) }, output);
        Require(code == 1 && visited == 3 && output.ToString().EndsWith("1/3 tests passed" + Environment.NewLine, StringComparison.Ordinal), "Failure count or traversal changed.");
    }
    private static void Success()
    {
        using var output = new StringWriter();
        Require(TestReport.Run(new (string, Action)[] { ("ordinary", () => { }) }, output) == 0, "Success status changed.");
        Require(output.ToString() == "PASS  ordinary" + Environment.NewLine + "1/1 tests passed" + Environment.NewLine, "Successful output changed.");
        output.Write("still open");
    }
    private static void Empty()
    {
        using var output = new StringWriter();
        Require(TestReport.Run(Array.Empty<(string, Action)>(), output) == 0 && output.ToString() == "0/0 tests passed" + Environment.NewLine, "Empty legacy contract changed.");
    }
    private static void NoData()
    {
        using var output = new StringWriter();
        var error = new IOException("controlled fixture"); error.Data["private-data-key"] = "PRIVATE_DATA_CANARY";
        Require(TestReport.Run(new (string, Action)[] { ("data", () => throw error) }, output) == 1, "Failure lost.");
        Require(!output.ToString().Contains("PRIVATE_DATA_CANARY") && !output.ToString().Contains("private-data-key"), "Exception.Data was dumped.");
    }
}
