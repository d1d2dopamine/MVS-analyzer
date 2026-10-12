using System.Security.Cryptography;
using System.Text.Json;
using MvsAnalyzer;

internal static class HuberNumericalChecks
{
    // Independent analytic root: the first four residuals are unclipped, the last
    // contributes c, and MAD=2, so mu=(0+1+2+7+2*c*K)/4.
    private const double BaseRoot = 3.497049991945017345;
    private const double K = 1.482602218505602;
    private static readonly double[] Base = { 0, 1, 2, 7, 30 };

    public static readonly (string Name, Action Run)[] All =
    {
        ("Staged Huber repairs unit, offset and outlier regressions", UnitsOffsetsOutliers),
        ("Staged Huber handles finite extreme coordinates and exact symmetry", ExtremeCoordinates),
        ("Staged Huber distinguishes positive subnormal MAD from exact zero", SubnormalMad),
        ("Staged Huber falls back only for a strict-majority exact zero MAD", ZeroMadPolicy),
        ("Staged Huber reports invalid input and iteration failure without a value", UnavailableResults),
        ("Staged Huber preserves input, permutation and reflection behavior", OrderAndReflection),
        ("Staged Huber native export uses the same solver and explicit provenance", ExportAgreement),
        ("Staged Huber failure export retains null and unavailable status", ExportFailure),
        ("Staged Huber repair preserves active twelve metric results and identities", ActiveMetricsUnchanged)
    };

    private static void UnitsOffsetsOutliers()
    {
        foreach (double unit in new[] { 1e-14, 1e-13, 1e-10, 1e-6, 1, 1e6, 1e12 })
            NearRoot(Converged(Base.Select(x => x * unit).ToArray()).Value, BaseRoot * unit, 2 * K * unit);
        foreach (double shift in new[] { 1e4, 1e9, 1e12, 3e12, -3e12 })
            NearRoot(Converged(Base.Select(x => x + shift).ToArray()).Value, BaseRoot + shift, 2 * K);
        foreach (double outlier in new[] { 1e13, double.MaxValue })
            NearRoot(Converged(new[] { 0d, 1, 2, 7, outlier }).Value, BaseRoot, 2 * K);
        foreach (int exponent in new[] { -1070, -1022, -900, -500, 500, 1019 })
            NearRoot(Converged(Base.Select(x => Math.ScaleB(x, exponent)).ToArray()).Value,
                Math.ScaleB(BaseRoot, exponent), Math.ScaleB(2 * K, exponent));
    }

    private static void ExtremeCoordinates()
    {
        double maximum = double.MaxValue;
        double ulp = maximum - Math.BitDecrement(maximum);
        foreach (double magnitude in new[] { double.Epsilon, 1e-300, 1d, 1e300, maximum })
        {
            Check(Converged(new[] { -magnitude, magnitude }).Value == 0, "Symmetric pair must be exactly zero.");
            Check(Converged(new[] { -magnitude, -magnitude, magnitude, magnitude }).Value == 0,
                "Symmetric even sample must be exactly zero, even when raw MAD/scale overflows.");
            Check(Converged(new[] { -magnitude, 0, magnitude }).Value == 0, "Symmetric odd sample must be exactly zero.");
        }
        // All five residuals are unclipped; the exact mean/root is -maximum/20.
        double asymmetric = Converged(new[] { -maximum, -maximum, maximum / 4, maximum / 2, maximum }).Value;
        NearRoot(asymmetric / maximum, -.05, .75 * K);
        // Original-scale subtraction overflows and recovery requires cancellation.
        NearRoot(Converged(new[] { -maximum, -maximum, -maximum / 2, maximum, maximum }).Value,
            -3.031509952958732e307, maximum / 2 * K);
        NearRoot(Converged(new[] { maximum - 30 * ulp, maximum - 7 * ulp,
            maximum - 2 * ulp, maximum - ulp, maximum }).Value, maximum - BaseRoot * ulp, 2 * K * ulp);
        double tinyUnit = 16 * double.Epsilon;
        NearRoot(Converged(new[] { 0d, tinyUnit, 2 * tinyUnit, 7 * tinyUnit, maximum }).Value,
            BaseRoot * tinyUnit, 2 * K * tinyUnit);
    }

    private static void SubnormalMad()
    {
        double d = double.Epsilon;
        // The exact median and MAD are d/2, although neither is a binary64 value.
        var half = Converged(new[] { 0d, d });
        Check(half.Value == 0 && half.Iterations == 1, "Half-subnormal midpoint must round to even zero after convergence.");
        Check(Converged(new[] { -d, 0d }).Value == 0, "Reflected half-subnormal midpoint must round to zero.");
        Check(Converged(new[] { -d, d }).Value == 0, "Opposite subnormals must retain positive MAD and symmetry.");
        Check(Converged(new[] { 0d, 0d, d, d }).Value == 0, "Exactly half ties have a positive MAD, not a fallback.");
        Check(Converged(new[] { 0d, 0d, 0d, d, d, d }).Value == 0, "Repeated half ties still have positive MAD.");
        NearRoot(Converged(new[] { 0d, d, d, 2 * d }).Value, d, d);
        NearRoot(Converged(new[] { 0d, 16 * d, 32 * d, 112 * d, double.MaxValue }).Value, 56 * d, 32 * K * d);
    }

    private static void ZeroMadPolicy()
    {
        foreach (double value in new[] { -double.MaxValue, -4d, -double.Epsilon, 0d, double.Epsilon, 4d, double.MaxValue })
        {
            Fallback(new[] { value, value }, value);
            Fallback(new[] { value, value, value, value, value }, value);
            Fallback(new[] { value, value, value, -double.MaxValue, double.MaxValue }, value);
            Fallback(new[] { value, value, value, value == 0 ? 1 : 0 }, value);
        }
        Fallback(new[] { -0d, 0d, -0d, 1d }, 0);
        Converged(new[] { 0d, 0, 1, 1 });
        Converged(new[] { 0d, 1, 1, 2 });
    }

    private static void UnavailableResults()
    {
        foreach (double[] values in new[] { Array.Empty<double>(), new[] { 1d }, new[] { 0d, double.NaN },
            new[] { 0d, double.PositiveInfinity }, new[] { double.NegativeInfinity, 1d } })
        {
            long[] before = values.Select(BitConverter.DoubleToInt64Bits).ToArray();
            var result = MetricRegistry.HuberLocation(values);
            Check(double.IsNaN(result.Value) && result.Status == "invalid_input" && result.Iterations == 0,
                "Invalid input needs unavailable value and explicit status.");
            Check(double.IsNaN(MetricRegistry.Compute("huber_location", values)), "Compute accepted invalid input.");
            Check(before.SequenceEqual(values.Select(BitConverter.DoubleToInt64Bits)), "Invalid input was mutated.");
        }
        var failed = MetricRegistry.HuberLocation(Base, 1);
        Check(double.IsNaN(failed.Value) && failed.Status == "iteration_limit" && failed.Iterations == 1,
            "Budget exhaustion must not return the last iterate or a median fallback.");
        Converged(Base);
        foreach (int budget in new[] { 0, -1, 65, int.MaxValue })
        {
            bool threw = false;
            try { MetricRegistry.HuberLocation(Base, budget); }
            catch (ArgumentOutOfRangeException) { threw = true; }
            Check(threw, "The internal test budget must be bounded to 1..64.");
        }
    }

    private static void OrderAndReflection()
    {
        double maximum = double.MaxValue, d = double.Epsilon;
        var samples = new[]
        {
            Base, new[] { 0d, 16 * d, 32 * d, 112 * d, maximum },
            new[] { -maximum, -maximum, maximum / 4, maximum / 2, maximum },
            new[] { -maximum, -maximum, -maximum / 2, maximum, maximum },
            new[] { 0d, 0, 1, 1 }, new[] { 0d, 1, 1, 2 }, new[] { 0d, d }
        };
        foreach (double[] values in samples)
        {
            var expected = Converged(values);
            foreach (double[] permutation in Permutations(values))
            {
                var result = Converged(permutation);
                Check(result.Value == expected.Value && result.Iterations == expected.Iterations,
                    "Sorting must make value and iteration count permutation independent.");
            }
            var reflected = Converged(values.Select(x => -x).ToArray());
            // Reflection can change the upper-median anchor for even samples. The
            // independent expanded oracle checks each exact binary64 input separately.
            double unit = values.Max(x => Math.Abs(x));
            if (unit <= 32 * d) NearRoot(reflected.Value, -expected.Value, 32 * d);
            else NearRoot(reflected.Value / unit, -expected.Value / unit, 1);
        }
    }

    private static void ExportAgreement()
    {
        WithExport(new[] { Base, new[] { 0d, double.Epsilon }, new[] { 4d, 4, 4 },
            new[] { -double.MaxValue, -double.MaxValue, double.MaxValue, double.MaxValue } }, null,
            (document, fixtureBytes) =>
            {
                JsonElement root = document.RootElement;
                Check(root.GetProperty("schema").GetString() == "MVS-HUBER-NATIVE-1", "Native schema changed.");
                Check(root.GetProperty("implementationId").GetString() == MetricRegistry.HuberImplementationId,
                    "Implementation provenance is missing.");
                Check(root.GetProperty("fixtureSha256").GetString() == Sha(fixtureBytes), "Fixture checksum mismatch.");
                Check(root.GetProperty("coreAssemblySha256").GetString() == Sha(File.ReadAllBytes(typeof(AnalysisEngine).Assembly.Location)),
                    "Core assembly checksum mismatch.");
                Check(root.GetProperty("nativeRuntime").GetString() == Environment.Version.ToString(), "Runtime provenance mismatch.");
                Check(root.GetProperty("metricStaged").GetBoolean() && root.GetProperty("activeMetricCount").GetInt32() == 12,
                    "Staged or active-family provenance changed.");
                Check(root.GetProperty("engineVersion").GetString() == "1.6.2", "Engine identity changed.");
                var arrays = new[] { Base, new[] { 0d, double.Epsilon }, new[] { 4d, 4, 4 },
                    new[] { -double.MaxValue, -double.MaxValue, double.MaxValue, double.MaxValue } };
                int index = 0;
                foreach (JsonElement row in root.GetProperty("results").EnumerateArray())
                {
                    var solver = MetricRegistry.HuberLocation(arrays[index]);
                    Check(row.GetProperty("id").GetString() == "case_" + index, "Case identity/order changed.");
                    Check(row.GetProperty("status").GetString() == "finite", "Successful export is not finite.");
                    Check(row.GetProperty("value").GetDouble() == MetricRegistry.Compute("huber_location", arrays[index]),
                        "Export and Compute did not use the same solver.");
                    Check(row.GetProperty("solverStatus").GetString() == solver.Status &&
                        row.GetProperty("iterations").GetInt32() == solver.Iterations, "Solver diagnostics disagree.");
                    index++;
                }
                Check(index == arrays.Length, "Export omitted a fixture.");
            });
    }

    private static void ExportFailure()
    {
        WithExport(new[] { Base }, 1, (document, _) =>
        {
            JsonElement row = document.RootElement.GetProperty("results")[0];
            Check(row.GetProperty("value").ValueKind == JsonValueKind.Null &&
                row.GetProperty("status").GetString() == "unavailable" &&
                row.GetProperty("solverStatus").GetString() == "iteration_limit" &&
                row.GetProperty("iterations").GetInt32() == 1, "Failed solve must export null with explicit failure provenance.");
        });
    }

    private static void ActiveMetricsUnchanged()
    {
        string[] frozen = { "median", "standard_deviation", "coefficient_of_variation", "mad", "iqr", "normalized_mad",
            "normalized_iqr", "mean", "rms", "range", "geometric_mean", "trimmed_mean_20" };
        Check(MetricRegistry.LegacyKeys.SequenceEqual(frozen) && AnalysisEngine.MetricKeys.SequenceEqual(frozen),
            "The active twelve-metric order changed.");
        Check(MetricRegistry.All.Take(12).All(x => x.LegacyInference) && MetricRegistry.All.Skip(12).All(x => !x.LegacyInference),
            "Active/staged flags changed.");
        Check(MetricRegistry.All.Select(x => x.Key).SequenceEqual(frozen.Concat(new[] { "huber_location", "hodges_lehmann", "qn", "log_sd" })),
            "The full metric registry order changed.");
        double[] input = { 1, 2, 3, 4, 5 };
        double[] expected = { 3, Math.Sqrt(2.5), Math.Sqrt(2.5) / 3, 1, 2, 1d / 3, 2d / 3,
            3, Math.Sqrt(11), 4, Math.Exp(Math.Log(120) / 5), 3 };
        double[] legacy = MetricRegistry.ComputeLegacy(input);
        for (int i = 0; i < frozen.Length; i++)
        {
            Check(Math.Abs(legacy[i] - expected[i]) <= 1e-13, "Active analytic value changed: " + frozen[i]);
            Check(MetricRegistry.Compute(frozen[i], input) == legacy[i], "Compute no longer agrees with active legacy: " + frozen[i]);
        }
        Check(AnalysisEngine.EngineVersion == "1.6.2" && OutputExporter.FormulaVersion == "MVS-1.4.0" &&
            OutputExporter.FormulaHash == "10a1e72218bd65ec024fc981aab9b9d0a9de8ac00db9188f9d80d54e1170598c",
            "Staged arithmetic changed active engine/formula identity.");
    }

    private static MetricRegistry.HuberResult Converged(double[] values)
    {
        long[] before = values.Select(BitConverter.DoubleToInt64Bits).ToArray();
        var result = MetricRegistry.HuberLocation(values);
        Check(result.Status == "converged" && result.Iterations >= 1 && result.Iterations <= 64 && double.IsFinite(result.Value),
            $"Positive-MAD solve was not converged: {result.Status}, {result.Iterations}, {result.Value:R}.");
        Check(result.Value >= values.Min() && result.Value <= values.Max(), "Converged root left the input hull.");
        Check(result.Value == MetricRegistry.Compute("huber_location", values), "Compute/solver result mismatch.");
        Check(before.SequenceEqual(values.Select(BitConverter.DoubleToInt64Bits)), "Caller input was mutated.");
        return result;
    }

    private static void Fallback(double[] values, double expected)
    {
        long[] before = values.Select(BitConverter.DoubleToInt64Bits).ToArray();
        var result = MetricRegistry.HuberLocation(values);
        Check(result.Status == "zero_mad_fallback" && result.Iterations == 0 && result.Value == expected,
            "Exact zero MAD did not use the declared fallback.");
        Check(MetricRegistry.Compute("huber_location", values) == result.Value, "Fallback Compute/solver mismatch.");
        Check(before.SequenceEqual(values.Select(BitConverter.DoubleToInt64Bits)), "Fallback mutated caller input.");
    }

    private static void NearRoot(double actual, double expected, double fixedMadScale)
    {
        double magnitude = Math.Abs(expected);
        double ulp = magnitude == double.MaxValue ? magnitude - Math.BitDecrement(magnitude) : Math.BitIncrement(magnitude) - magnitude;
        double tolerance = Math.Max(1e-10 * fixedMadScale, 4 * ulp);
        Check(double.IsFinite(actual) && Math.Abs(actual - expected) <= tolerance,
            $"Huber {actual:R} differs from analytic/reference {expected:R}, tolerance {tolerance:R}.");
    }

    private static IEnumerable<double[]> Permutations(double[] values)
    {
        if (values.Length == 0) { yield return Array.Empty<double>(); yield break; }
        for (int index = 0; index < values.Length; index++)
            foreach (double[] tail in Permutations(values.Where((_, i) => i != index).ToArray()))
                yield return new[] { values[index] }.Concat(tail).ToArray();
    }

    private static void WithExport(double[][] values, int? budget, Action<JsonDocument, byte[]> check)
    {
        string directory = Path.Combine(Path.GetTempPath(), "mvs_huber_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try
        {
            string fixture = Path.Combine(directory, "fixtures.json"), output = Path.Combine(directory, "native.json");
            byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(new { schema = "MVS-HUBER-REFERENCE-1",
                cases = values.Select((x, i) => new { id = "case_" + i, values = x }) });
            File.WriteAllBytes(fixture, bytes);
            if (budget is int limit) HuberDiagnosticChecks.ExportWithIterationBudgetForTesting(fixture, output, limit);
            else HuberDiagnosticChecks.Export(fixture, output);
            using var document = JsonDocument.Parse(File.ReadAllBytes(output));
            check(document, bytes);
        }
        finally { Directory.Delete(directory, true); }
    }

    private static string Sha(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    private static void Check(bool condition, string message) { if (!condition) throw new Exception(message); }
}
