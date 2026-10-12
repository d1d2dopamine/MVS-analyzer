using MvsAnalyzer;

internal static class CliArgumentChecks
{
    public static readonly (string Name, Action Run)[] All = {
        ("CLI boolean values are explicit and case insensitive", BooleanValues),
        ("Malformed global flags cannot hide behind earlier valid flags", MalformedDuplicates),
        ("Single-dash option values cannot become help flags", SingleDashValues),
        ("Boolean switches do not consume a following help flag", SwitchBoundaries),
        ("JSON error intent is nonthrowing and order independent", JsonErrorIntent),
        ("CLI value and validation boundaries remain strict", ValueBoundaries)
    };

    private static readonly string[] GlobalFlags = { "--json", "--quiet", "--help", "-h", "--version" };

    private static void BooleanValues()
    {
        foreach (string flag in GlobalFlags)
        {
            Check(new CliArguments(new[] { "version", flag }).Flag(flag), flag + " was not enabled.");
            Check(new CliArguments(new[] { "version", flag.ToUpperInvariant() + "=TrUe" }).Flag(flag), flag + " lost case-insensitive true.");
            Check(!new CliArguments(new[] { "version", flag + "=FALSE" }).Flag(flag), flag + " ignored explicit false.");
            Check(!new CliArguments(new[] { "version" }).Flag(flag), flag + " was enabled while absent.");
            foreach (string value in new[] { "", "banana", "1", "0" })
                Throws(() => new CliArguments(new[] { "version", flag + "=" + value }).Flag(flag), flag + " accepted an invalid boolean.");
        }
    }

    private static void MalformedDuplicates()
    {
        foreach (string flag in GlobalFlags)
        {
            foreach (string valid in new[] { flag, flag + "=true", flag + "=false" })
            {
                Throws(() => new CliArguments(new[] { "version", valid, flag + "=banana" }).Flag(flag), flag + " hid a later invalid value.");
                Throws(() => new CliArguments(new[] { "version", flag + "=banana", valid }).Flag(flag), flag + " hid an earlier invalid value.");
            }
            // Informational commands retain the first valid occurrence; this repair does not
            // introduce a new duplicate-option policy for commands that do not call Validate.
            Check(!new CliArguments(new[] { "version", flag + "=false", flag }).Flag(flag), flag + " no longer uses the first valid value.");
            Check(new CliArguments(new[] { "version", flag, flag + "=false" }).Flag(flag), flag + " no longer uses the first valid value.");
        }
    }

    private static void SingleDashValues()
    {
        foreach (string option in new[] { "--project", "--description", "--in", "--out", "--id" })
        foreach (string value in new[] { "-h", "-H", "-h=true", "-h=false", "-h=banana" })
        {
            var args = new CliArguments(new[] { "analyze", option, value, "--json" });
            Check(args.Value(option) == value, "The single-dash value was changed.");
            Check(!args.Flag("-h"), option + " value became a help flag.");
            Check(args.Flag("--json") && args.FlagRequested("--json"), "A value hid the following JSON flag.");
            args.Validate(new[] { option });
        }
        var attached = new CliArguments(new[] { "analyze", "--project=-h=banana", "--description=--json=banana" });
        Check(!attached.Flag("-h") && !attached.Flag("--json") && !attached.FlagRequested("--json"), "An attached value became a flag.");
        var laterHelp = new CliArguments(new[] { "analyze", "--project", "-h", "-h" });
        Check(laterHelp.Flag("-h"), "A real help flag after the value was hidden.");
    }

    private static void SwitchBoundaries()
    {
        foreach (string flag in new[] { "--split", "--local-settings", "--allow-group-scoped-ids", "--overwrite", "--force",
            "--mean-time", "--scale-time", "--correlate", "--no-random-scale", "--include-entity-ids", "--normalize",
            "--json", "--quiet", "--help", "--version" })
        {
            Check(new CliArguments(new[] { "analyze", flag, "-h" }).Flag("-h"), flag + " consumed the following help flag.");
            Check(new CliArguments(new[] { "analyze", flag.ToUpperInvariant() + "=false", "-h" }).Flag("-h"), flag + "=false consumed the help flag.");
        }
        Check(new CliArguments(new[] { "-h", "--json" }).Flag("-h"), "Options-only help stopped working.");
    }

    private static void JsonErrorIntent()
    {
        foreach (string[] tokens in new[] {
            new[] { "version", "--json" }, new[] { "version", "--JSON=TRUE" },
            new[] { "version", "--json=banana" }, new[] { "version", "--json=" },
            new[] { "version", "--json=false", "--json=banana" },
            new[] { "version", "--json=banana", "--json=false" },
            new[] { "version", "--json=false", "--json" },
            new[] { "version", "--json", "--json=false" },
            new[] { "version", "--quiet=banana", "--json" },
            new[] { "version", "--json", "--quiet=banana" }
        }) Check(new CliArguments(tokens).FlagRequested("--json"), "Explicit JSON error intent was lost: " + string.Join(" ", tokens));

        foreach (string[] tokens in new[] {
            new[] { "version" }, new[] { "version", "--JSON=FALSE" },
            new[] { "version", "--json=false", "--quiet=banana" },
            new[] { "version", "--quiet=banana", "--json=false" },
            new[] { "version", "--json=false", "--JSON=FALSE" },
            new[] { "analyze", "--description=--json=banana" }
        }) Check(!new CliArguments(tokens).FlagRequested("--json"), "JSON error output was requested without intent: " + string.Join(" ", tokens));
    }

    private static void ValueBoundaries()
    {
        var args = new CliArguments(new[] { "estimation", "--location", "-10.5", "--seed", "-7", "--json=false" });
        Check(args.Number("--location", 0) == -10.5 && args.Int("--seed", 0) == -7, "Negative numbers were mistaken for options.");
        Check(!args.Flag("-h") && !args.Flag("--json"), "A negative number changed a boolean flag.");
        args.Validate(new[] { "--location", "--seed" });
        Throws(() => new CliArguments(new[] { "estimation", "--location", "--json" }).Number("--location", 0), "A missing numeric value used its default.");
        Throws(() => new CliArguments(new[] { "analyze", "--project", "--json" }).Validate(new[] { "--project" }), "A following option was consumed as a required value.");
        Throws(() => new CliArguments(new[] { "analyze", "--typo=value" }).Validate(new[] { "--project" }), "Unknown-option rejection changed.");
        Throws(() => new CliArguments(new[] { "analyze", "--json", "--json=false" }).Validate(Array.Empty<string>()), "Duplicate-option rejection changed.");
    }

    private static void Check(bool condition, string message) { if (!condition) throw new Exception(message); }
    private static void Throws(Action action, string message)
    {
        try { action(); }
        catch (ArgumentException) { return; }
        throw new Exception(message);
    }
}
