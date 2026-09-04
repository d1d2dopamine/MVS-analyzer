using System.Globalization;

namespace MvsAnalyzer;

/// <summary>
/// Argument reading for the headless commands. It is written out by hand for the same reason the
/// benchmark entry point is: a parser package would add a dependency to babysit to a program that
/// has deliberately kept its dependency list empty.
///
/// Two shapes are accepted for every option, "--out folder" and "--out=folder", because the second
/// is what people type inside notebook cells where a stray space is easy to miss.
/// </summary>
internal sealed class CliArguments
{
    private readonly string[] tokens;

    public CliArguments(string[] tokens) => this.tokens = tokens ?? Array.Empty<string>();

    /// <summary>The first token when it is not an option, lowercased. Empty when only options were passed.</summary>
    public string Command =>
        tokens.Length > 0 && !tokens[0].StartsWith("-", StringComparison.Ordinal)
            ? tokens[0].ToLowerInvariant()
            : "";

    public bool Flag(string name)
    {
        foreach (string token in tokens)
            if (string.Equals(token, name, StringComparison.OrdinalIgnoreCase)) return true;
        return false;
    }

    public string? Value(string name)
    {
        for (int i = 0; i < tokens.Length; i++)
        {
            if (string.Equals(tokens[i], name, StringComparison.OrdinalIgnoreCase))
                return i + 1 < tokens.Length && !tokens[i + 1].StartsWith("--", StringComparison.Ordinal)
                    ? tokens[i + 1]
                    : null;
            if (tokens[i].StartsWith(name + "=", StringComparison.OrdinalIgnoreCase))
                return tokens[i].Substring(name.Length + 1);
        }
        return null;
    }

    /// <summary>Reads a required path or identifier, or throws with a sentence that says what to type.</summary>
    public string Require(string name)
    {
        string? value = Value(name);
        if (string.IsNullOrWhiteSpace(value))
            throw new ArgumentException("Pass " + name + " <value>.");
        return value.Trim();
    }

    public int Int(string name, int fallback)
    {
        string? value = Value(name);
        if (value == null) return fallback;
        return int.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out int parsed)
            ? parsed
            : fallback;
    }

    /// <summary>
    /// Numbers are read with the invariant culture on purpose. A machine whose locale writes a
    /// decimal comma would otherwise silently turn --effect 1.15 into 115.
    /// </summary>
    public double Number(string name, double fallback)
    {
        string? value = Value(name);
        if (value == null) return fallback;
        return double.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out double parsed)
            ? parsed
            : fallback;
    }

    public bool Has(string name) => Value(name) != null || Flag(name);
}
