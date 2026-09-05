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
        {
            if (string.Equals(token, name, StringComparison.OrdinalIgnoreCase)) return true;
            if (token.StartsWith(name + "=", StringComparison.OrdinalIgnoreCase))
            { if (bool.TryParse(token[(name.Length + 1)..], out bool enabled)) return enabled; throw new ArgumentException(name + " is a boolean flag."); }
        }
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
        if (value == null) { if (Flag(name)) throw new ArgumentException(name + " requires a value."); return fallback; }
        if (!int.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out int parsed))
            throw new ArgumentException(name + " requires an integer, got: " + value);
        return parsed;
    }

    /// <summary>
    /// Numbers are read with the invariant culture on purpose. A machine whose locale writes a
    /// decimal comma would otherwise silently turn --effect 1.15 into 115.
    /// </summary>
    public double Number(string name, double fallback)
    {
        string? value = Value(name);
        if (value == null) { if (Flag(name)) throw new ArgumentException(name + " requires a value."); return fallback; }
        if (!double.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out double parsed) || !double.IsFinite(parsed))
            throw new ArgumentException(name + " requires a finite number, got: " + value);
        return parsed;
    }

    public bool Has(string name) => Value(name) != null || Flag(name);
    public void Validate(IEnumerable<string> allowed)
    {
        var names = allowed.ToHashSet(StringComparer.OrdinalIgnoreCase);
        var switches = new HashSet<string>(new[] { "--split", "--local-settings", "--allow-group-scoped-ids", "--overwrite", "--force", "--mean-time", "--scale-time", "--correlate", "--no-random-scale", "--include-entity-ids", "--normalize" }, StringComparer.OrdinalIgnoreCase);
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        for (int i = Command.Length > 0 ? 1 : 0; i < tokens.Length; i++)
        {
            string token = tokens[i];
            if (!token.StartsWith("--", StringComparison.Ordinal)) throw new ArgumentException("Unexpected positional argument: " + token + ". Use a named option.");
            string name = token.Split('=', 2)[0];
            if (!names.Contains(name)) throw new ArgumentException("Unknown option for this command: " + name);
            if (!seen.Add(name)) throw new ArgumentException("Duplicate option: " + name);
            if (switches.Contains(name)) { _ = Flag(name); continue; }
            if (token.Contains('=')) continue;
            if (i + 1 >= tokens.Length || tokens[i + 1].StartsWith("--", StringComparison.Ordinal)) throw new ArgumentException(name + " requires a value.");
            i++;
        }
    }
}
