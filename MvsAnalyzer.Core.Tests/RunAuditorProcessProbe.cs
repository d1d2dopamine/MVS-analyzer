using System.Diagnostics;
using System.Text;
using System.Text.Json;
using MvsAnalyzer;

// Explicit test-harness entry point only; never called by the production CLI.
internal static class RunAuditorProcessProbe
{
    internal static int Run(string requestFile)
    {
        using JsonDocument doc = JsonDocument.Parse(File.ReadAllText(requestFile));
        JsonElement request = doc.RootElement;
        string Text(string key) => request.GetProperty(key).GetString()!;
        int Count(string key, int fallback) => request.TryGetProperty(key, out var value) ? value.GetInt32() : fallback;
        string mode = Text("mode"), output = Text("output"), ready = Text("ready"), gate = Text("gate");
        var watch = Stopwatch.StartNew();
        try
        {
            NewText(ready, Environment.ProcessId.ToString());
            WaitFor(gate);
            if (mode == "append")
            {
                int count = Count("count", 1), size = Count("payloadChars", 0);
                if (count < 1 || count > 32 || size < 0 || size > 65536) throw new ArgumentOutOfRangeException("Probe bounds");
                var ids = new List<string>();
                for (int i = 0; i < count; i++)
                {
                    string id = Text("writer") + "-" + i.ToString("D3");
                    RunAuditor.AppendJournal(id, Text("auditRoot"), "synthetic", new AppSettings(), 100, new string('x', size));
                    ids.Add(id);
                    Thread.Sleep(1);
                }
                NewJson(output, new { mode, ids, elapsedSeconds = watch.Elapsed.TotalSeconds });
            }
            else if (mode == "read")
            {
                var observations = new List<object>();
                int count = Count("count", 1);
                if (count < 1 || count > 128) throw new ArgumentOutOfRangeException("Probe bounds");
                if (request.TryGetProperty("reading", out var reading)) NewText(reading.GetString()!, "about-to-read");
                for (int i = 0; i < count; i++)
                {
                    AuditReport report = RunAuditor.Audit(Text("auditRoot"));
                    observations.Add(new { report.JournalEntries, journalFindings = report.Findings.Where(f => f.Code.StartsWith("JOURNAL_", StringComparison.Ordinal)).ToArray() });
                    Thread.Sleep(1);
                }
                NewJson(output, new { mode, observations, elapsedSeconds = watch.Elapsed.TotalSeconds });
            }
            else if (mode == "held-partial")
            {
                string path = RunAuditor.JournalPath;
                Directory.CreateDirectory(Path.GetDirectoryName(path)!);
                using (RunAuditor.AcquireJournalLock(path))
                {
                    string line = JsonSerializer.Serialize(new { runId = "held-000", folder = Text("auditRoot"), datasetHash = "synthetic", candidateSet = "", seed = 1, effect = 1.15, scenario = "location", alpha = .05, previous = "genesis" });
                    byte[] bytes = Encoding.UTF8.GetBytes(line + "\n");
                    using var stream = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.ReadWrite);
                    stream.Write(bytes, 0, 1); stream.Flush(true);
                    NewText(Text("partialReady"), "partial-written-under-journal-mutex");
                    WaitFor(Text("finishGate"), 15);
                    stream.Write(bytes, 1, bytes.Length - 1); stream.Flush(true);
                }
                NewJson(output, new { mode, elapsedSeconds = watch.Elapsed.TotalSeconds });
            }
            else throw new ArgumentException("Unknown probe mode.");
            return 0;
        }
        catch (Exception error)
        {
            NewJson(output, new { mode, errorType = error.GetType().Name, error = error.Message, elapsedSeconds = watch.Elapsed.TotalSeconds });
            return 1;
        }
    }

    private static void NewText(string path, string text)
    {
        using var stream = new FileStream(path, FileMode.CreateNew, FileAccess.Write);
        using var writer = new StreamWriter(stream, new UTF8Encoding(false));
        writer.Write(text);
    }
    private static void NewJson(string path, object value) => NewText(path, JsonSerializer.Serialize(value, new JsonSerializerOptions { WriteIndented = true }));
    private static void WaitFor(string path, int seconds = 10)
    {
        var timer = Stopwatch.StartNew();
        while (!File.Exists(path))
        {
            if (timer.Elapsed > TimeSpan.FromSeconds(seconds)) throw new TimeoutException("Probe gate did not open.");
            Thread.Sleep(5);
        }
    }
}
