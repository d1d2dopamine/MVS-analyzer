using System.IO.Compression;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace MvsAnalyzer;

internal sealed class PluginManifest
{
    public string Id { get; set; } = "";
    public string Name { get; set; } = "";
    public string Version { get; set; } = "1.0.0";
    public string Author { get; set; } = "Unknown";
    public string Type { get; set; } = "visualization";
    public string Description { get; set; } = "";
    public string MinAppVersion { get; set; } = "0.6.0";
    public string PackageHash { get; set; } = "";
    public bool Enabled { get; set; } = true;
    public string Folder { get; set; } = "";
}

internal static class PluginManager
{
    private static string Root => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MVS_Analyzer", "plugins");
    private static readonly string[] Forbidden = { ".dll", ".exe", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".hta", ".com", ".scr" };

    public static List<PluginManifest> ListInstalled()
    {
        Directory.CreateDirectory(Root); var output = new List<PluginManifest>();
        foreach (string file in Directory.GetFiles(Root, "plugin.json", SearchOption.AllDirectories))
        {
            try
            {
                PluginManifest? manifest = JsonSerializer.Deserialize<PluginManifest>(File.ReadAllText(file), JsonOptions()); if (manifest == null) continue;
                manifest.Folder = Path.GetDirectoryName(file)!; manifest.Enabled = !File.Exists(Path.Combine(manifest.Folder, "disabled.flag"));
                string hashFile = Path.Combine(manifest.Folder, "package.sha256"); if (File.Exists(hashFile)) manifest.PackageHash = File.ReadAllText(hashFile).Trim(); output.Add(manifest);
            }
            catch { }
        }
        return output.OrderBy(x => x.Name).ToList();
    }

    private const long MaxUnpackedBytes = 64L * 1024 * 1024;
    private const int MaxEntries = 2000;

    public static PluginManifest Install(string archivePath)
    {
        Directory.CreateDirectory(Root); string hash = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(archivePath))).ToLowerInvariant();
        using var archive = ZipFile.OpenRead(archivePath); ZipArchiveEntry? manifestEntry = archive.Entries.FirstOrDefault(e => string.Equals(e.FullName.Replace('\\','/'), "plugin.json", StringComparison.OrdinalIgnoreCase));
        if (manifestEntry == null) throw new InvalidDataException("plugin.json was not found at the package root.");
        if (archive.Entries.Count > MaxEntries) throw new InvalidDataException($"The package contains more than {MaxEntries} files.");
        if (archive.Entries.Sum(e => e.Length) > MaxUnpackedBytes) throw new InvalidDataException("The unpacked package would exceed 64 MB.");
        foreach (ZipArchiveEntry entry in archive.Entries)
        {
            string normalized = entry.FullName.Replace('\\', '/');
            if (normalized.StartsWith('/') || normalized.Contains("../", StringComparison.Ordinal) || Forbidden.Contains(Path.GetExtension(normalized), StringComparer.OrdinalIgnoreCase)) throw new InvalidDataException($"Unsafe plugin entry: {entry.FullName}");
        }
        PluginManifest? manifest; using (var reader = new StreamReader(manifestEntry.Open())) manifest = JsonSerializer.Deserialize<PluginManifest>(reader.ReadToEnd(), JsonOptions());
        if (manifest == null || !Regex.IsMatch(manifest.Id, "^[a-z0-9][a-z0-9._-]{2,63}$")) throw new InvalidDataException("Plugin id must contain 3–64 lowercase letters, digits, dots, underscores or hyphens.");
        if (manifest.Type is not ("visualization" or "import-export")) throw new InvalidDataException("Only visualization and import-export plugins are allowed.");
        if (!Version.TryParse(manifest.MinAppVersion, out Version? required)) required = new Version(0, 0);
        if (required > Version.Parse(AnalysisEngine.EngineVersion)) throw new InvalidDataException($"This plugin requires MVS Analyzer {manifest.MinAppVersion} or newer.");
        string target = Path.Combine(Root, manifest.Id); string temp = target + ".installing"; if (Directory.Exists(temp)) Directory.Delete(temp, true); Directory.CreateDirectory(temp);
        foreach (ZipArchiveEntry entry in archive.Entries)
        {
            if (string.IsNullOrEmpty(entry.Name)) continue; string destination = Path.GetFullPath(Path.Combine(temp, entry.FullName)); if (!destination.StartsWith(Path.GetFullPath(temp) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("Unsafe plugin path.");
            Directory.CreateDirectory(Path.GetDirectoryName(destination)!); entry.ExtractToFile(destination, true);
        }
        File.WriteAllText(Path.Combine(temp, "package.sha256"), hash); if (Directory.Exists(target)) Directory.Delete(target, true); Directory.Move(temp, target);
        manifest.PackageHash = hash; manifest.Folder = target; manifest.Enabled = true; return manifest;
    }

    public static void SetEnabled(PluginManifest plugin, bool enabled)
    {
        string flag = Path.Combine(plugin.Folder, "disabled.flag"); if (enabled) { if (File.Exists(flag)) File.Delete(flag); } else File.WriteAllText(flag, "disabled");
    }
    public static void Remove(PluginManifest plugin) { if (Directory.Exists(plugin.Folder)) Directory.Delete(plugin.Folder, true); }
    public static IEnumerable<string> EnabledTemplateFiles() => ListInstalled().Where(x => x.Enabled && x.Type == "visualization").SelectMany(x => Directory.Exists(Path.Combine(x.Folder, "templates")) ? Directory.GetFiles(Path.Combine(x.Folder, "templates"), "*.json") : Array.Empty<string>());
    private static JsonSerializerOptions JsonOptions() => new() { PropertyNameCaseInsensitive = true, WriteIndented = true };
}
