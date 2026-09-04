using System.Globalization;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;

namespace MvsAnalyzer.Benchmarking;

/// <summary>
/// Records the machine a run happened on, and answers one narrow question: would another
/// machine produce the same floating point numbers?
///
/// This matters because the benchmark advertises bit-identical replay. That claim is honest
/// only inside one environment. Every replication owns its own random stream, so thread count
/// and scheduling cannot change a result, but Math.Log, Math.Exp, Math.Pow and Math.Cos are not
/// required by IEEE-754 to be correctly rounded, and .NET does not promise identical results
/// across operating systems, architectures or runtime versions. Math.Sqrt is the exception; it
/// is required to be exact. Once the same protocol can run on a laptop and in a hosted notebook,
/// a determinism hash that differs between the two is expected, not a bug, and the only way to
/// tell that apart from a real regression is to record where the numbers were produced.
///
/// The fingerprint deliberately leaves the operating system build string out. A Windows patch
/// level changes that string without changing a single arithmetic result, and a hash that moves
/// for cosmetic reasons teaches its reader to ignore it. What goes in is the architecture, the
/// runtime version and the measured output of the functions that are actually allowed to differ.
/// </summary>
internal static class BenchmarkEnvironment
{
    /// <summary>What replay guarantees. Written into every manifest next to the determinism hash.</summary>
    public const string Scope = "withinEnvironment";

    /// <summary>
    /// Inputs are ordinary magnitudes taken from the code that actually calls these functions:
    /// the lognormal data generator, the Box-Muller transform, the gamma tail used by the
    /// Kruskal-Wallis p-value, and the five powers inside the composite score.
    /// </summary>
    public static double[] ProbeValues() => new[]
    {
        Math.Log(2.5),
        Math.Log(1e-8),
        Math.Log(1.0 + 1e-12),
        Math.Exp(1.75),
        Math.Exp(-9.5),
        Math.Exp(0.18 * 0.7071067811865476),
        Math.Pow(1.15, 0.30),
        Math.Pow(0.42, 0.25),
        Math.Pow(0.9995, 0.15),
        Math.Cos(1.2345),
        Math.Cos(6.2831853071795862),
        Math.Sqrt(2.0),
    };

    /// <summary>A human readable line for reports and for the console banner.</summary>
    public static string Describe() =>
        RuntimeInformation.OSDescription.Trim() + "  |  " +
        RuntimeInformation.OSArchitecture + "  |  process " + RuntimeInformation.ProcessArchitecture +
        "  |  .NET " + Environment.Version;

    /// <summary>The exact text the hash is taken over, so a mismatch can be diffed instead of guessed at.</summary>
    public static string Fingerprint()
    {
        var text = new StringBuilder();
        text.Append("osArchitecture=").Append(RuntimeInformation.OSArchitecture).Append(';');
        text.Append("processArchitecture=").Append(RuntimeInformation.ProcessArchitecture).Append(';');
        text.Append("runtime=").Append(Environment.Version.ToString()).Append(';');
        text.Append("probe=");
        foreach (double value in ProbeValues())
            text.Append(value.ToString("R", CultureInfo.InvariantCulture)).Append(',');
        return text.ToString();
    }

    /// <summary>
    /// Sixteen hex characters is enough to notice a change and short enough to read out loud in an
    /// issue report. The full fingerprint is recoverable from the manifest, so nothing is lost.
    /// </summary>
    public static string Hash =>
        Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(Fingerprint()))).ToLowerInvariant();

    public static string ShortHash => Hash.Substring(0, 16);
}
