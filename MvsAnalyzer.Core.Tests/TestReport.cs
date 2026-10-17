// Test executable diagnostics only; never serializes environment or Exception.Data.
internal static class TestReport
{
    internal static int Run(IEnumerable<(string Name, Action Run)> tests, TextWriter output)
    {
        int total = 0, failed = 0;
        foreach (var test in tests)
        {
            total++;
            try { test.Run(); output.WriteLine($"PASS  {test.Name}"); }
            catch (Exception error)
            {
                failed++;
                output.WriteLine($"FAIL  {test.Name}: {error.Message}");
                output.WriteLine("DETAIL " + error.ToString());
            }
        }
        output.WriteLine($"{total - failed}/{total} tests passed");
        return failed == 0 ? 0 : 1;
    }
}
