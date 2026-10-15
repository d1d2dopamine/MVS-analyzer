namespace MvsAnalyzer;

/// <summary>
/// Resolves the root before MVS_Analyzer. An explicit override is independent of
/// OS-specific appdata variables; without it each caller retains its legacy option.
/// Resolution never creates a directory or falls back after an invalid override.
/// </summary>
internal static class ApplicationDataPaths
{
    internal const string OverrideVariable = "MVS_APPDATA_ROOT";

    internal static string GetLocalApplicationData(
        Environment.SpecialFolderOption option = Environment.SpecialFolderOption.None) =>
        ResolveLocalApplicationData(Environment.GetEnvironmentVariable(OverrideVariable), option);

    internal static string ResolveLocalApplicationData(string? overrideRoot,
        Environment.SpecialFolderOption option = Environment.SpecialFolderOption.None)
    {
        if (overrideRoot is null)
            return Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData, option);
        if (string.IsNullOrWhiteSpace(overrideRoot) || !Path.IsPathFullyQualified(overrideRoot))
            throw new DirectoryNotFoundException("MVS_APPDATA_ROOT must be a nonempty absolute directory path.");
        // GetFullPath also rejects invalid path syntax before any caller can write.
        return Path.GetFullPath(overrideRoot);
    }
}
