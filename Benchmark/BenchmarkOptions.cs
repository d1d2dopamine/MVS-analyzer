namespace MvsAnalyzer.Benchmarking;

/// <summary>
/// Benchmark preferences live in their own file next to the application settings. They are kept
/// separate on purpose: the benchmark is a developer tool and must not be able to disturb the
/// settings that scientific runs depend on.
/// </summary>
internal sealed class BenchmarkOptions
{
    public string ProfileId { get; set; } = "quick";
    public int Seed { get; set; } = 20260904;
    public string OutputFolder { get; set; } = "";
    public string RealDataFolder { get; set; } = "";

    private static string Folder => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MVS_Analyzer");

    private static string FilePath => Path.Combine(Folder, "benchmark.txt");

    public static BenchmarkOptions Load()
    {
        var options = new BenchmarkOptions();
        try
        {
            if (!File.Exists(FilePath)) return options;
            foreach (string line in File.ReadAllLines(FilePath))
            {
                int split = line.IndexOf('=');
                if (split <= 0) continue;
                string key = line.Substring(0, split).Trim();
                string value = line.Substring(split + 1).Trim();
                switch (key)
                {
                    case "profile": options.ProfileId = value; break;
                    case "seed": if (int.TryParse(value, out int seed) && seed > 0) options.Seed = seed; break;
                    case "output": options.OutputFolder = value; break;
                    case "realdata": options.RealDataFolder = value; break;
                }
            }
        }
        catch (Exception)
        {
            // A damaged preferences file must never stop the program from opening.
        }
        return options;
    }

    public void Save()
    {
        try
        {
            Directory.CreateDirectory(Folder);
            var lines = new List<string>
            {
                "profile=" + ProfileId,
                "seed=" + Seed.ToString(System.Globalization.CultureInfo.InvariantCulture),
                "output=" + OutputFolder,
                "realdata=" + RealDataFolder
            };
            File.WriteAllLines(FilePath, lines);
        }
        catch (Exception)
        {
            // Preferences are a convenience, not a requirement.
        }
    }
}
