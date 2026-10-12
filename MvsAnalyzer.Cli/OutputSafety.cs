namespace MvsAnalyzer.Cli;

/// <summary>
/// Read-only preflight for commands that write fixed names into an output folder.
/// This guards predictable path collisions, not concurrent filesystem changes or
/// unexpected failures during the later, individually atomic output writes.
/// </summary>
internal static class OutputSafety
{
    internal static readonly string[] CalibrationFiles = { "calibration.csv", "calibration_tracks.csv", "calibration_recommendations.csv", "calibration_state.json" };
    internal static readonly string[] VarianceFiles = { "variance_report.json", "variance_components.csv", "variance_tests.csv", "run_manifest.json" };
    internal static readonly string[] MelsmFiles = { "melsm_report.json", "melsm_parameters.csv", "melsm_random_effects.csv", "run_manifest.json" };
    internal static readonly string[] EstimationFiles = { "estimation_report.json", "estimation_performance.csv", "estimation_draws.csv", "run_manifest.json" };

    internal static void Preflight(string folder, IEnumerable<string> outputNames, IEnumerable<string?> protectedInputs, bool overwrite, bool requireEmptyDirectory = false)
    {
        string resolvedFolder = ResolvePath(folder, directory: true);
        string[] inputs = protectedInputs.Where(p => p != null).Select(p => ResolvePath(p!)).ToArray();
        // macOS commonly uses a case-insensitive filesystem. Conservatively reject
        // case-only aliases there even if this particular volume is case-sensitive.
        StringComparison comparison = OperatingSystem.IsWindows() || OperatingSystem.IsMacOS()
            ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        foreach (string name in outputNames)
        {
            string target = Path.Combine(resolvedFolder, name);
            if (inputs.Any(input => string.Equals(input, target, comparison)))
                throw new InvalidDataException("An output target would replace an input file: " + target + ". Choose a different output folder; --overwrite does not allow replacing inputs.");
            FileAttributes? attributes = Attributes(target);
            if (attributes == null) continue;
            // A leaf symlink would be replaced, not followed, by AtomicText. Reject
            // it deliberately rather than silently changing a user's link layout.
            // Portable FileAttributes cannot classify every Unix FIFO/socket type.
            if ((attributes.Value & (FileAttributes.Directory | FileAttributes.ReparsePoint | FileAttributes.Device)) != 0)
                throw new InvalidDataException("An output target is a directory, link or unsupported entry: " + target + ". Choose a different output folder.");
            if (!overwrite)
                throw new InvalidDataException("An output file already exists: " + target + ". Choose another output folder or pass --overwrite.");
        }
        if (requireEmptyDirectory && !overwrite && Directory.Exists(folder) && Directory.EnumerateFileSystemEntries(folder).Any())
            throw new InvalidDataException("The output directory is not empty. Use a new directory or explicitly pass --overwrite.");
    }

    private static FileAttributes? Attributes(string path)
    {
        try { return File.GetAttributes(path); }
        catch (FileNotFoundException) { return null; }
        catch (DirectoryNotFoundException) { return null; }
    }

    private static string ResolvePath(string path, bool directory = false)
    {
        int links = 0;
        return ResolveAbsolutePath(Path.GetFullPath(path), directory, ref links);
    }

    private static string ResolveAbsolutePath(string path, bool directory, ref int links)
    {
        string root = Path.GetPathRoot(path)!;
        string current = root;
        string[] parts = path[root.Length..].Split(new[] { Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar }, StringSplitOptions.RemoveEmptyEntries);
        for (int i = 0; i < parts.Length; i++)
        {
            if (parts[i] == ".") continue;
            if (parts[i] == "..") { current = Path.GetDirectoryName(current) ?? root; continue; }
            current = Path.Combine(current, parts[i]);
            FileAttributes? attributes = Attributes(current);
            if (attributes != null && (attributes.Value & FileAttributes.ReparsePoint) != 0)
            {
                if (++links > 64) throw new InvalidDataException("Too many filesystem links while resolving: " + path);
                FileSystemInfo info = (attributes.Value & FileAttributes.Directory) != 0 ? new DirectoryInfo(current) : new FileInfo(current);
                string target = info.LinkTarget
                    ?? throw new InvalidDataException("Unsupported filesystem link: " + current);
                if (Path.IsPathRooted(target) && !Path.IsPathFullyQualified(target))
                    throw new InvalidDataException("Unsupported root-relative filesystem link: " + current);
                // Keep '..' in the raw link target until preceding components have
                // been resolved. Lexically collapsing it can hide a real alias.
                current = ResolveAbsolutePath(Path.IsPathFullyQualified(target) ? target : Path.Combine(Path.GetDirectoryName(current)!, target), directory: false, ref links);
                attributes = Attributes(current);
                if (attributes == null) throw new InvalidDataException("A filesystem link has no existing target: " + path);
            }
            if ((directory || i < parts.Length - 1) && attributes != null && (attributes.Value & FileAttributes.Directory) == 0)
                throw new InvalidDataException("An output or input parent path is not a directory: " + current);
        }
        return Path.TrimEndingDirectorySeparator(current);
    }
}
