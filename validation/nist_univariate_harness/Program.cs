using System.Globalization;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using MvsAnalyzer;

namespace MvsNistUnivariateHarness;

// Test-only friend assembly: the production metric implementations are called
// directly, without copying formulas or changing the supplied value sequence.
internal static class Program
{
    private const string InputSchema = "mvs-nist-input/v1";
    private const string OutputSchema = "mvs-nist-native/v1";
    private const int MaximumInputBytes = 16 * 1024 * 1024;
    private const int MaximumCases = 12;
    private const int MaximumValuesPerCase = 10_000;
    private const int MaximumTotalValues = 20_000;
    private const NumberStyles DecimalStyles = NumberStyles.AllowLeadingSign
        | NumberStyles.AllowDecimalPoint | NumberStyles.AllowExponent;

    private sealed record InputCase(string Id, string SourceSha256, double[] Values);

    private static int Main(string[] args)
    {
        string output;
        int exitCode;
        try
        {
            // Finish validation, computation, and serialization before writing
            // anything, so a later failing case cannot emit partial success.
            output = JsonSerializer.Serialize(Run(args));
            exitCode = 0;
        }
        catch (Exception error)
        {
            output = JsonSerializer.Serialize(new
            {
                schema = OutputSchema,
                status = "failed",
                error = new { type = error.GetType().FullName, message = error.Message }
            });
            exitCode = 1;
        }

        Console.Out.WriteLine(output);
        return exitCode;
    }

    private static object Run(string[] args)
    {
        if (args.Length != 2 || args[0] != "--input" || string.IsNullOrEmpty(args[1]))
            throw new ArgumentException("Usage: NistUnivariateHarness --input PATH");

        // Open the input only once. Parsing and hashing use this same immutable
        // byte buffer, never a second read of a potentially changed input file.
        byte[] inputBytes = ReadBoundedInput(args[1]);
        string inputSha256 = Sha256(inputBytes);
        List<InputCase> inputCases = ParseInput(inputBytes);

        // These identities are SHA-256 hashes of the physical harness and core
        // assembly DLLs loaded for this process, not of their source files.
        string harnessSha256 = AssemblySha256(typeof(Program).Assembly.Location);
        string coreSha256 = AssemblySha256(typeof(MetricRegistry).Assembly.Location);
        var results = new List<object>(inputCases.Count);
        foreach (InputCase input in inputCases)
        {
            var inputBits = new string[input.Values.Length];
            for (int index = 0; index < input.Values.Length; index++)
                inputBits[index] = Bits(input.Values[index]);

            double mean = MetricRegistry.Compute("mean", input.Values);
            double standardDeviation = MetricRegistry.Compute("standard_deviation", input.Values);
            if (!double.IsFinite(mean) || !double.IsFinite(standardDeviation))
                throw new InvalidDataException($"Case '{input.Id}' produced a nonfinite metric result.");

            results.Add(new
            {
                id = input.Id,
                sourceSha256 = input.SourceSha256,
                count = input.Values.Length,
                mean,
                standardDeviation,
                meanBits = Bits(mean),
                standardDeviationBits = Bits(standardDeviation),
                inputBits
            });
        }

        return new
        {
            schema = OutputSchema,
            status = "completed",
            inputSha256,
            harnessSha256,
            coreSha256,
            runtimeVersion = Environment.Version.ToString(),
            architecture = RuntimeInformation.ProcessArchitecture.ToString().ToLowerInvariant(),
            cases = results
        };
    }

    private static byte[] ReadBoundedInput(string path)
    {
        using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        if (stream.Length > MaximumInputBytes)
            throw new InvalidDataException($"Input exceeds the {MaximumInputBytes}-byte limit.");

        using var buffer = new MemoryStream();
        var chunk = new byte[8192];
        int read;
        while ((read = stream.Read(chunk, 0, chunk.Length)) != 0)
        {
            if (buffer.Length + read > MaximumInputBytes)
                throw new InvalidDataException($"Input exceeds the {MaximumInputBytes}-byte limit.");
            buffer.Write(chunk, 0, read);
        }
        return buffer.ToArray();
    }

    private static List<InputCase> ParseInput(byte[] inputBytes)
    {
        using JsonDocument document = JsonDocument.Parse(inputBytes, new JsonDocumentOptions
        {
            AllowTrailingCommas = false,
            CommentHandling = JsonCommentHandling.Disallow,
            MaxDepth = 8
        });
        JsonElement root = document.RootElement;
        RequireExactFields(root, "input", "schema", "cases");
        if (RequireString(root.GetProperty("schema"), "schema") != InputSchema)
            throw new InvalidDataException($"Expected schema '{InputSchema}'.");

        JsonElement cases = root.GetProperty("cases");
        RequireArray(cases, "cases");
        if (cases.GetArrayLength() is < 1 or > MaximumCases)
            throw new InvalidDataException($"Expected between 1 and {MaximumCases} cases.");

        var parsed = new List<InputCase>(cases.GetArrayLength());
        var identifiers = new HashSet<string>(StringComparer.Ordinal);
        int totalValues = 0;
        foreach (JsonElement item in cases.EnumerateArray())
        {
            RequireExactFields(item, "case", "id", "sourceSha256", "values");
            string id = RequireString(item.GetProperty("id"), "case.id");
            if (!identifiers.Add(id))
                throw new InvalidDataException($"Duplicate case id '{id}'.");

            string sourceSha256 = RequireString(item.GetProperty("sourceSha256"), "case.sourceSha256");
            if (sourceSha256.Length != 64 || sourceSha256.Any(c => !IsLowerHexDigit(c)))
                throw new InvalidDataException($"Case '{id}' requires a 64-character lowercase hexadecimal sourceSha256.");

            JsonElement values = item.GetProperty("values");
            RequireArray(values, "case.values");
            int count = values.GetArrayLength();
            if (count is < 2 or > MaximumValuesPerCase)
                throw new InvalidDataException($"Case '{id}' requires between 2 and {MaximumValuesPerCase} values.");
            totalValues += count;
            if (totalValues > MaximumTotalValues)
                throw new InvalidDataException($"Input exceeds the {MaximumTotalValues}-value total limit.");

            var numbers = new double[count];
            int index = 0;
            foreach (JsonElement value in values.EnumerateArray())
            {
                string decimalText = RequireString(value, $"case '{id}' value {index}");
                if (!IsDecimalString(decimalText)
                    || !double.TryParse(decimalText, DecimalStyles, CultureInfo.InvariantCulture, out double number)
                    || !double.IsFinite(number))
                    throw new InvalidDataException($"Case '{id}' value {index} must be a finite invariant-culture decimal string.");
                numbers[index++] = number;
            }
            parsed.Add(new InputCase(id, sourceSha256, numbers));
        }
        return parsed;
    }

    private static void RequireExactFields(JsonElement element, string context, params string[] required)
    {
        if (element.ValueKind != JsonValueKind.Object)
            throw new InvalidDataException($"{context} must be an object.");

        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (JsonProperty property in element.EnumerateObject())
        {
            if (!seen.Add(property.Name))
                throw new InvalidDataException($"Duplicate {context} field '{property.Name}'.");
            if (!required.Contains(property.Name, StringComparer.Ordinal))
                throw new InvalidDataException($"Unknown {context} field '{property.Name}'.");
        }
        foreach (string field in required)
        {
            if (!seen.Contains(field))
                throw new InvalidDataException($"Missing {context} field '{field}'.");
        }
    }

    private static string RequireString(JsonElement value, string context)
    {
        if (value.ValueKind != JsonValueKind.String)
            throw new InvalidDataException($"{context} must be a string.");
        return value.GetString()!;
    }

    private static void RequireArray(JsonElement value, string context)
    {
        if (value.ValueKind != JsonValueKind.Array)
            throw new InvalidDataException($"{context} must be an array.");
    }

    // Decimal grammar: [+-]?(digits[.digits?]?|.digits)([eE][+-]?digits)?
    // Digits are ASCII; whitespace, group separators, and named floats fail.
    private static bool IsDecimalString(string value)
    {
        int index = 0;
        if (index < value.Length && value[index] is '+' or '-') index++;
        int digits = 0;
        while (index < value.Length && IsDigit(value[index])) { index++; digits++; }
        if (index < value.Length && value[index] == '.')
        {
            index++;
            while (index < value.Length && IsDigit(value[index])) { index++; digits++; }
        }
        if (digits == 0) return false;
        if (index < value.Length && value[index] is 'e' or 'E')
        {
            index++;
            if (index < value.Length && value[index] is '+' or '-') index++;
            int exponentStart = index;
            while (index < value.Length && IsDigit(value[index])) index++;
            if (index == exponentStart) return false;
        }
        return index == value.Length;
    }

    private static bool IsDigit(char value) => value is >= '0' and <= '9';

    private static bool IsLowerHexDigit(char value) => IsDigit(value) || value is >= 'a' and <= 'f';

    // Exactly 16 lowercase hex characters encode the unsigned IEEE-754 binary64
    // bit pattern, most-significant digit first, independent of machine endianness.
    private static string Bits(double value) =>
        unchecked((ulong)BitConverter.DoubleToInt64Bits(value)).ToString("x16", CultureInfo.InvariantCulture);

    private static string Sha256(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();

    private static string AssemblySha256(string path)
    {
        if (string.IsNullOrEmpty(path))
            throw new InvalidOperationException("A physical assembly path is required for SHA-256 identification.");
        using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
    }
}
