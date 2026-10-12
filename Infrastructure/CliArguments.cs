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
    private static readonly HashSet<string> switches = new(new[] {
        "--split", "--local-settings", "--allow-group-scoped-ids", "--overwrite", "--force",
        "--mean-time", "--scale-time", "--correlate", "--no-random-scale", "--include-entity-ids",
        "--normalize", "--json", "--quiet", "--help", "-h", "--version"
    }, StringComparer.OrdinalIgnoreCase);

    public CliArguments(string[] tokens) => this.tokens = tokens ?? Array.Empty<string>();

    /// <summary>The first token when it is not an option, lowercased. Empty when only options were passed.</summary>
    public string Command =>
        tokens.Length > 0 && !tokens[0].StartsWith("-", StringComparison.Ordinal)
            ? tokens[0].ToLowerInvariant()
            : "";

    public bool Flag(string name)
    {
        bool? first = null;
        foreach (string token in OptionTokens())
        {
            if (string.Equals(token, name, StringComparison.OrdinalIgnoreCase)) first ??= true;
            else if (token.StartsWith(name + "=", StringComparison.OrdinalIgnoreCase))
            {
                if (!bool.TryParse(token[(name.Length + 1)..], out bool enabled))
                    throw new ArgumentException(name + " is a boolean flag.");
                first ??= enabled;
            }
        }
        return first ?? false;
    }

    /// <summary>
    /// Nonthrowing selection of the error-output channel. An explicit flag, including a malformed
    /// equals value, requests that channel unless its value is valid false. Check every occurrence
    /// so an invalid value or a later true request is not hidden by an earlier false. This does not
    /// validate the option: callers must still use Flag before executing a command.
    /// </summary>
    public bool FlagRequested(string name) => OptionTokens().Any(token =>
        string.Equals(token, name, StringComparison.OrdinalIgnoreCase) ||
        (token.StartsWith(name + "=", StringComparison.OrdinalIgnoreCase) &&
            (!bool.TryParse(token[(name.Length + 1)..], out bool enabled) || enabled)));

    private IEnumerable<string> OptionTokens()
    {
        for (int i = Command.Length > 0 ? 1 : 0; i < tokens.Length; i++)
        {
            string token = tokens[i];
            if (!token.StartsWith("-", StringComparison.Ordinal)) continue;
            yield return token;
            // Match Value/Validate: a named value may begin with a single dash (for example
            // --project -h or --location -10). Such a value must not become a global flag.
            if (token.StartsWith("--", StringComparison.Ordinal) && !token.Contains('=') &&
                !switches.Contains(token) && i + 1 < tokens.Length &&
                !tokens[i + 1].StartsWith("--", StringComparison.Ordinal)) i++;
        }
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
        names.Add("--json");
        names.Add("--quiet");
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
