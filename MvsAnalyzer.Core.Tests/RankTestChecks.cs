using System.Security.Cryptography;
using System.Text.Json;

namespace MvsAnalyzer;

/// <summary>Calls the real Core methods against independently frozen SciPy values.</summary>
internal static class RankTestChecks
{
    internal static IEnumerable<(string Name, Action Run)> All
    {
        get
        {
            yield return ("Native Mann-Whitney matches independent asymptotic fixtures", () => References("mann_whitney"));
            yield return ("Native Kruskal-Wallis matches independent chi-square fixtures", () => References("kruskal_wallis"));
            yield return ("Constant and empty rank inputs retain explicit MVS policies", Policies);
            yield return ("Native rank p-values preserve group/order/affine invariances", Invariances);
        }
    }

    private static JsonDocument Fixture()
    {
        string path = Path.Combine(AppContext.BaseDirectory, "rank-test-fixtures-v1.json");
        byte[] bytes = File.ReadAllBytes(path);
        // Updated only after independent fixture review; no engine-derived expected values.
        string hash = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
        Check(hash == "41cdf8528ae2af97da7a25273c5a5bd156270b63734923a40ae774a49053b781", "The independent rank fixture changed; review its provenance.");
        var document = JsonDocument.Parse(bytes);
        Check(document.RootElement.GetProperty("schema").GetString() == "mvs-rank-reference/v1", "Unknown rank fixture schema.");
        return document;
    }

    private static double[][] Groups(JsonElement row) => row.GetProperty("groups").EnumerateArray()
        .Select(group => group.EnumerateArray().Select(x => x.GetDouble()).ToArray()).ToArray();

    private static double Native(string method, double[][] groups) => method switch
    {
        "mann_whitney" => AnalysisEngine.MannWhitneyP(groups[0], groups[1]),
        "kruskal_wallis" => AnalysisEngine.KruskalWallisP(groups),
        _ => throw new InvalidDataException("Unknown rank method: " + method)
    };

    private static void References(string method)
    {
        using var document = Fixture();
        double tolerance = method == "mann_whitney" ? 2e-7 : 2e-10;
        Check(document.RootElement.GetProperty("absoluteTolerance").GetProperty(method).GetDouble() == tolerance,
            "The independent accuracy gate changed.");
        int count = 0;
        foreach (var row in document.RootElement.GetProperty("cases").EnumerateArray())
        {
            if (row.GetProperty("method").GetString() != method || row.GetProperty("reference").GetString() != "scipy") continue;
            double expected = row.GetProperty("expectedP").GetDouble();
            double actual = Native(method, Groups(row));
            string id = row.GetProperty("id").GetString()!;
            Check(double.IsFinite(actual) && actual >= 0 && actual <= 1, id + ": nonfinite/out-of-range p-value.");
            Check(Math.Abs(actual - expected) <= tolerance, $"{id}: native p={actual:R}, independent p={expected:R}, absolute gate={tolerance:R}.");
            count++;
        }
        Check(count == (method == "mann_whitney" ? 25 : 24), "Missing independent " + method + " cases.");
        Console.WriteLine($"  {count} independent {method} references checked (absolute p-value gate).");
    }

    private static void Policies()
    {
        using var document = Fixture();
        int count = 0;
        foreach (var row in document.RootElement.GetProperty("cases").EnumerateArray())
        {
            if (row.GetProperty("reference").GetString() != "mvs-declared-policy") continue;
            double actual = Native(row.GetProperty("method").GetString()!, Groups(row));
            var expected = row.GetProperty("expectedP");
            string id = row.GetProperty("id").GetString()!;
            Check(expected.ValueKind == JsonValueKind.Null ? double.IsNaN(actual) : actual == expected.GetDouble(),
                id + ": declared empty/constant policy changed.");
            count++;
        }
        Check(count == 4, "Missing explicit empty/constant policies.");
    }

    private static void Invariances()
    {
        using var document = Fixture();
        foreach (var row in document.RootElement.GetProperty("cases").EnumerateArray())
        {
            if (row.GetProperty("reference").GetString() != "scipy") continue;
            string method = row.GetProperty("method").GetString()!;
            string id = row.GetProperty("id").GetString()!;
            double[][] groups = Groups(row);
            double baseline = Native(method, groups);
            var variants = new[]
            {
                groups.Reverse().ToArray(),
                groups.Select(g => g.Reverse().ToArray()).ToArray(),
                groups.Select(g => g.Select(x => x * 8 + 64).ToArray()).ToArray(),
                groups.Select(g => g.Select(x => -x).ToArray()).ToArray()
            };
            foreach (double[][] variant in variants)
                Check(Math.Abs(Native(method, variant) - baseline) <= 1e-12, id + ": rank invariance failed.");
        }
    }

    private static void Check(bool condition, string message)
    {
        if (!condition) throw new InvalidDataException(message);
    }
}
