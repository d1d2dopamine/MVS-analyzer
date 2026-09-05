using System.Text.Json;

namespace MvsAnalyzer;

internal sealed record ColabWireDescriptor(string Name, int Major, int Minor, int MinimumPeerMinor, string[] Capabilities);

internal sealed class ColabProtocolException : Exception
{
    public int HttpStatus { get; }
    public string Code { get; }
    public ColabProtocolException(int status, string code, string message) : base(message) { HttpStatus = status; Code = code; }
}

/// <summary>
/// Transport compatibility is independent of a UI/release label. Additive updates keep Major;
/// incompatible changes need a new Major or an explicit adapter. Scientific contracts remain strict.
/// </summary>
internal static class ColabCompatibility
{
    public const string Name = "mvs-colab";
    public const int Major = 1, Minor = 0;
    public static ColabWireDescriptor Wire => new(Name, Major, Minor, 0,
        new[] { "job-zip-v1", "commands-v1", "status-sequence-v1", "status-retry-v1", "runtime-bundle-v1" });

    private static JsonElement Field(JsonElement root, string name)
    {
        if (root.ValueKind == JsonValueKind.Object)
            foreach (JsonProperty property in root.EnumerateObject())
                if (property.Name.Equals(name, StringComparison.OrdinalIgnoreCase)) return property.Value;
        return default;
    }

    public static void ValidatePeer(JsonElement packet, string legacyRevision)
    {
        JsonElement wire = Field(packet, "transport");
        if (wire.ValueKind == JsonValueKind.Undefined)
        {
            // Known adapter only. Never silently accept an unknown old notebook protocol.
            if (legacyRevision == "ui-colab-3") return;
            throw new ColabProtocolException(426, "notebook_update_required",
                "This notebook uses an unsupported legacy connection format. Open the notebook shipped with MVS once; UI version strings are not a compatibility contract.");
        }
        if (wire.ValueKind != JsonValueKind.Object || Field(wire, "name").ValueKind != JsonValueKind.String || Field(wire, "name").GetString() != Name ||
            !Field(wire, "major").TryGetInt32Safe(out int major) || major != Major ||
            !Field(wire, "minor").TryGetInt32Safe(out int minor) || minor < 0 ||
            !Field(wire, "minimumPeerMinor").TryGetInt32Safe(out int required) || required < 0 || required > Minor)
            throw new ColabProtocolException(426, "incompatible_transport", "The notebook needs an incompatible transport version. Update the desktop and notebook together.");
        JsonElement features = Field(wire, "capabilities");
        if (features.ValueKind != JsonValueKind.Array || features.GetArrayLength() > 100 || features.EnumerateArray().Any(x => x.ValueKind != JsonValueKind.String))
            throw new ColabProtocolException(426, "missing_capability", "The notebook did not advertise its connection capabilities.");
        var available = features.EnumerateArray().Where(x => x.ValueKind == JsonValueKind.String).Select(x => x.GetString()!).ToHashSet(StringComparer.Ordinal);
        if (!available.Contains("commands-v1") || !available.Contains("status-sequence-v1"))
            throw new ColabProtocolException(426, "missing_capability", "The notebook lacks reliable command acknowledgement/status sequencing.");
    }

    private static bool TryGetInt32Safe(this JsonElement value, out int result)
    {
        result = 0; return value.ValueKind == JsonValueKind.Number && value.TryGetInt32(out result);
    }

    public static int PrintCliManifest()
    {
        Console.WriteLine(ScientificJson.Serialize(new
        {
            appVersion = ReleaseInfo.Version, engineVersion = ReleaseInfo.EngineVersion,
            formulaHash = OutputExporter.FormulaHash, stateSchema = ReleaseInfo.StateSchema,
            cliProtocol = new { name = "mvs-cli", major = 1, capabilities = new[] { "calibrate", "analyze", "state-check", "variance", "melsm", "estimation", "benchmark" } },
            transport = Wire
        }));
        return 0;
    }
}
