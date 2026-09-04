using System.Globalization;
using System.Text;
using System.Text.Json;

namespace MvsAnalyzer;

// Declarative contributions a plugin may add. None of them can execute code or
// touch the ten metrics or the frozen MVS formula.
internal sealed record ImportProfile(string Id, string Name, string Plugin, char Delimiter, bool DecimalComma, Dictionary<string, string[]> Columns);
internal sealed record SettingsProfile(string Id, string Name, string Plugin, Dictionary<string, string> Values);
internal sealed record ReportTemplate(string Id, string Name, string Plugin, string Body);
internal sealed record ValidationRule(string Id, string Plugin, string Target, double Min, double Max, string Message, string MessageRu);
internal sealed record PluginAssetError(string Plugin, string File, string Message);

internal sealed class PluginContributions
{
    public List<ImportProfile> ImportProfiles { get; } = new();
    public List<SettingsProfile> SettingsProfiles { get; } = new();
    public List<ReportTemplate> ReportTemplates { get; } = new();
    public List<ValidationRule> ValidationRules { get; } = new();
    public Dictionary<string, string> Terms { get; } = new(StringComparer.OrdinalIgnoreCase);
    public List<string> FigureTemplates { get; } = new();
    public List<PluginAssetError> Errors { get; } = new();
    public int Total => ImportProfiles.Count + SettingsProfiles.Count + ReportTemplates.Count + ValidationRules.Count + Terms.Count + FigureTemplates.Count;
}

internal static class PluginAssets
{
    private static PluginContributions? cache;
    public static PluginContributions Current => cache ??= Scan();
    public static void Invalidate() => cache = null;

    public static PluginContributions Scan()
    {
        var found = new PluginContributions();
        List<PluginManifest> plugins;
        try { plugins = PluginManager.ListInstalled(); }
        catch (Exception ex) { found.Errors.Add(new PluginAssetError("", "plugins", ex.Message)); return found; }
        foreach (PluginManifest plugin in plugins.Where(x => x.Enabled))
        {
            if (plugin.Type == "visualization") found.FigureTemplates.AddRange(Files(plugin, "templates", "*.json"));
            foreach (string file in Files(plugin, "import-profiles", "*.json"))
                Guard(found, plugin, file, () => found.ImportProfiles.Add(ReadImportProfile(plugin, file)));
            foreach (string file in Files(plugin, "settings-profiles", "*.json"))
                Guard(found, plugin, file, () => found.SettingsProfiles.Add(ReadSettingsProfile(plugin, file)));
            foreach (string file in Files(plugin, "report-templates", "*.txt"))
                Guard(found, plugin, file, () => found.ReportTemplates.Add(new ReportTemplate(Path.GetFileNameWithoutExtension(file), Path.GetFileNameWithoutExtension(file), plugin.Name, File.ReadAllText(file))));
            foreach (string file in Files(plugin, "validation-rules", "*.json"))
                Guard(found, plugin, file, () => found.ValidationRules.AddRange(ReadRules(plugin, file)));
            foreach (string file in Files(plugin, "terms", "*.json"))
                Guard(found, plugin, file, () => ReadTerms(found, file));
        }
        return found;
    }

    private static void Guard(PluginContributions found, PluginManifest plugin, string file, Action action)
    {
        // A broken asset is reported by name instead of disappearing silently.
        try { action(); }
        catch (Exception ex) { found.Errors.Add(new PluginAssetError(plugin.Name, Path.GetFileName(file), ex.Message)); }
    }

    private static string[] Files(PluginManifest plugin, string sub, string mask)
    {
        string folder = Path.Combine(plugin.Folder, sub);
        return Directory.Exists(folder) ? Directory.GetFiles(folder, mask) : Array.Empty<string>();
    }

    private static ImportProfile ReadImportProfile(PluginManifest plugin, string file)
    {
        using JsonDocument doc = JsonDocument.Parse(File.ReadAllText(file));
        JsonElement root = doc.RootElement;
        string id = Str(root, "id", Path.GetFileNameWithoutExtension(file));
        var columns = new Dictionary<string, string[]>(StringComparer.OrdinalIgnoreCase);
        if (root.TryGetProperty("columns", out JsonElement cols) && cols.ValueKind == JsonValueKind.Object)
            foreach (JsonProperty property in cols.EnumerateObject())
            {
                var names = new List<string>();
                if (property.Value.ValueKind == JsonValueKind.Array)
                    foreach (JsonElement item in property.Value.EnumerateArray()) { string? v = item.GetString(); if (!string.IsNullOrWhiteSpace(v)) names.Add(v.Trim()); }
                else if (property.Value.ValueKind == JsonValueKind.String) { string? v = property.Value.GetString(); if (!string.IsNullOrWhiteSpace(v)) names.Add(v.Trim()); }
                if (names.Count > 0) columns[property.Name] = names.ToArray();
            }
        if (columns.Count == 0) throw new InvalidDataException("The profile declares no columns.");
        string delimiter = Str(root, "delimiter", "");
        char separator = delimiter.Length == 0 ? char.MinValue : delimiter == "\\t" ? '\t' : delimiter[0];
        bool decimalComma = root.TryGetProperty("decimalComma", out JsonElement dc) && dc.ValueKind == JsonValueKind.True;
        return new ImportProfile(id, Str(root, "name", id), plugin.Name, separator, decimalComma, columns);
    }

    private static SettingsProfile ReadSettingsProfile(PluginManifest plugin, string file)
    {
        using JsonDocument doc = JsonDocument.Parse(File.ReadAllText(file));
        JsonElement root = doc.RootElement;
        string id = Str(root, "id", Path.GetFileNameWithoutExtension(file));
        var values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        if (root.TryGetProperty("values", out JsonElement list) && list.ValueKind == JsonValueKind.Object)
            foreach (JsonProperty property in list.EnumerateObject()) values[property.Name] = Raw(property.Value);
        if (values.Count == 0) throw new InvalidDataException("The profile declares no values.");
        return new SettingsProfile(id, Str(root, "name", id), plugin.Name, values);
    }

    private static List<ValidationRule> ReadRules(PluginManifest plugin, string file)
    {
        using JsonDocument doc = JsonDocument.Parse(File.ReadAllText(file));
        var rules = new List<ValidationRule>();
        IEnumerable<JsonElement> items = doc.RootElement.ValueKind == JsonValueKind.Array
            ? doc.RootElement.EnumerateArray()
            : doc.RootElement.TryGetProperty("rules", out JsonElement inner) && inner.ValueKind == JsonValueKind.Array ? inner.EnumerateArray() : new[] { doc.RootElement };
        foreach (JsonElement item in items)
        {
            string target = Str(item, "target", "measurements").ToLowerInvariant();
            double min = Num(item, "min"), max = Num(item, "max");
            if (!double.IsFinite(min) && !double.IsFinite(max)) continue;
            string message = Str(item, "message", "Rule violated");
            rules.Add(new ValidationRule(Str(item, "id", Path.GetFileNameWithoutExtension(file)), plugin.Name, target, min, max, message, Str(item, "messageRu", message)));
        }
        if (rules.Count == 0) throw new InvalidDataException("No usable rule was found.");
        return rules;
    }

    private static void ReadTerms(PluginContributions found, string file)
    {
        using JsonDocument doc = JsonDocument.Parse(File.ReadAllText(file));
        if (doc.RootElement.ValueKind != JsonValueKind.Object) throw new InvalidDataException("A terminology file must be a flat object.");
        foreach (JsonProperty property in doc.RootElement.EnumerateObject())
            if (property.Value.ValueKind == JsonValueKind.String)
            {
                string? value = property.Value.GetString();
                if (!string.IsNullOrWhiteSpace(value)) found.Terms.TryAdd(property.Name, value.Trim());
            }
    }

    public static string Term(string key, string fallback) => Current.Terms.TryGetValue(key, out string? value) && value.Length > 0 ? value : fallback;

    // Applies only known settings keys and reports how many were accepted, so a
    // typo in a profile cannot silently change nothing.
    /// <summary>Settings a profile asked for but could not be given. Empty after a clean load.</summary>
    public static readonly List<string> SettingsWarnings = new();

    public static int Apply(SettingsProfile profile, AppSettings settings)
    {
        int applied = 0;
        foreach (KeyValuePair<string, string> pair in profile.Values)
        {
            string value = pair.Value.Trim();
            switch (pair.Key.ToLowerInvariant())
            {
                case "minvalue": if (int.TryParse(value, out int minValue)) { settings.MinValue = minValue; applied++; } break;
                case "maxvalue": if (int.TryParse(value, out int maxValue)) { settings.MaxValue = maxValue; applied++; } break;
                case "minmeasurements": if (int.TryParse(value, out int measurements)) { settings.MinMeasurements = Math.Clamp(measurements, 2, 100000); applied++; } break;
                case "calibrationseed": if (int.TryParse(value, out int seed)) { settings.CalibrationSeed = seed; applied++; } break;
                case "customrepetitions": if (int.TryParse(value, out int repetitions)) { settings.CustomRepetitions = Math.Clamp(repetitions, 100, 200000); applied++; } break;
                case "calibrationeffect": if (Dbl(value, out double effect)) { settings.CalibrationEffect = effect; applied++; } break;
                case "outlierrate": if (Dbl(value, out double outlier)) { settings.OutlierRate = Math.Clamp(outlier, 0, .25); applied++; } break;
                case "missingrate": if (Dbl(value, out double missing)) { settings.MissingRate = Math.Clamp(missing, 0, .50); applied++; } break;
                case "alpha": if (Dbl(value, out double alpha)) { settings.Alpha = Math.Clamp(alpha, .001, .20); applied++; } break;
                case "simulationscenario": if (SimulationScenarios.TryCanonical(value, out string scenarioName)) { settings.SimulationScenario = scenarioName; applied++; } else if (value.Length > 0) SettingsWarnings.Add("simulationScenario=" + value + " was rejected: unknown scenario, the previous setting was kept."); break;
                case "figuretemplates": if (value.Length > 0) { settings.FigureTemplates = value; applied++; } break;
                case "outputprefix": if (value.Length > 0) { settings.OutputPrefix = value; applied++; } break;
                case "generatefigures": settings.GenerateFigures = value == "true"; applied++; break;
            }
        }
        if (settings.MinValue >= settings.MaxValue) { settings.MinValue = -1000000; settings.MaxValue = 1000000; }
        return applied;
    }

    public static List<string> Check(AnalysisData data, bool russian)
    {
        var issues = new List<string>();
        foreach (ValidationRule rule in Current.ValidationRules)
        {
            int failed = rule.Target switch
            {
                "measurements" => data.Entities.Count(x => Outside(x.Measurements, rule)),
                "value" => data.Observations.Count(x => Outside(x.Value, rule)),
                "groupsize" => data.GroupCounts.Count(x => Outside(x, rule)),
                _ => 0
            };
            if (failed > 0) issues.Add((russian ? rule.MessageRu : rule.Message) + " — " + failed);
        }
        return issues;
    }
    private static bool Outside(double value, ValidationRule rule) => (double.IsFinite(rule.Min) && value < rule.Min) || (double.IsFinite(rule.Max) && value > rule.Max);

    // Report templates are plain text with {placeholders}; no expressions, no code.
    public static List<string> WriteReports(string folder, string runId, string project, string dataset, AnalysisData data, List<ResultRow> results, AppSettings settings)
    {
        var written = new List<string>();
        if (Current.ReportTemplates.Count == 0) return written;
        List<ResultRow> ranked = results.Where(x => double.IsFinite(x.Score)).OrderByDescending(x => x.Score).ToList();
        ResultRow? best = ranked.FirstOrDefault();
        var map = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["runId"] = runId,
            ["project"] = project,
            ["dataset"] = settings.AnonymousReports ? "[hidden]" : dataset,
            ["date"] = DateTime.Now.ToString("yyyy-MM-dd HH:mm", CultureInfo.InvariantCulture),
            ["entities"] = data.TotalEntities.ToString(CultureInfo.InvariantCulture),
            ["groups"] = string.Join(", ", data.GroupNames),
            ["measurement"] = data.MeasurementName,
            ["unit"] = data.Unit,
            ["engine"] = AnalysisEngine.EngineVersion,
            ["formula"] = OutputExporter.FormulaVersion,
            ["seed"] = settings.CalibrationSeed.ToString(CultureInfo.InvariantCulture),
            ["best"] = best?.Metric ?? "-",
            ["bestScore"] = best == null ? "-" : best.Score.ToString("0.0", CultureInfo.InvariantCulture),
            ["bestFpr"] = best == null ? "-" : best.Fpr.ToString("0.000", CultureInfo.InvariantCulture),
            ["bestPower"] = best == null ? "-" : best.Power.ToString("0.000", CultureInfo.InvariantCulture),
            ["candidates"] = string.Join(", ", results.Where(x => x.Candidate).Select(x => x.Metric)),
            ["ranking"] = string.Join(Environment.NewLine, ranked.Select((x, i) => (i + 1) + ". " + x.Metric + " — " + x.Score.ToString("0.0", CultureInfo.InvariantCulture)))
        };
        foreach (ReportTemplate template in Current.ReportTemplates)
        {
            try
            {
                var body = new StringBuilder(template.Body);
                foreach (KeyValuePair<string, string> pair in map) body.Replace("{" + pair.Key + "}", pair.Value);
                string path = Path.Combine(folder, "report_" + Safe(template.Id) + ".txt");
                File.WriteAllText(path, body.ToString(), new UTF8Encoding(true));
                written.Add(path);
            }
            catch (Exception ex) { Current.Errors.Add(new PluginAssetError(template.Plugin, template.Id, ex.Message)); }
        }
        return written;
    }

    private static string Safe(string value) { string clean = string.Concat(value.Where(c => char.IsLetterOrDigit(c) || c is '-' or '_')).Trim('_', '-'); return clean.Length == 0 ? "report" : clean; }
    private static bool Dbl(string value, out double result) => double.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out result) && double.IsFinite(result);
    private static double Num(JsonElement root, string name) => root.TryGetProperty(name, out JsonElement v) && v.ValueKind == JsonValueKind.Number && v.TryGetDouble(out double d) ? d : double.NaN;
    private static string Str(JsonElement root, string name, string fallback)
    {
        if (!root.TryGetProperty(name, out JsonElement value) || value.ValueKind != JsonValueKind.String) return fallback;
        string? text = value.GetString();
        return string.IsNullOrWhiteSpace(text) ? fallback : text.Trim();
    }
    private static string Raw(JsonElement value) => value.ValueKind switch
    {
        JsonValueKind.String => value.GetString() ?? "",
        JsonValueKind.Number => value.GetRawText(),
        JsonValueKind.True => "true",
        JsonValueKind.False => "false",
        _ => value.GetRawText()
    };
}
