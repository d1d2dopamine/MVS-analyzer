using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using MvsAnalyzer;

// Portable tests exercise the real loopback listener, not WinForms or a live Colab account.
internal static class ColabBridgeChecks
{
    internal static IEnumerable<(string Name, Action Run)> All => new (string, Action)[]
    {
        ("Colab HTTP bridge returns structured compatibility errors", StructuredFailure),
        ("Colab HTTP bridge restricts browser origins", OriginBoundary),
        ("Colab HTTP bridge supports local-network preflight", Preflight),
        ("Colab HTTP bridge rejects oversized bodies explicitly", OversizedBody),
    };
    private const string Origin = "https://colab.research.google.com";
    private static void Check(bool value, string message) { if (!value) throw new Exception(message); }
    private static HttpResponseMessage Request(ColabBridge bridge, string route, string origin = Origin, string method = "GET")
    {
        using var client = new HttpClient(new HttpClientHandler { UseProxy = false }) { Timeout = TimeSpan.FromSeconds(5) };
        using var request = new HttpRequestMessage(new HttpMethod(method), $"http://127.0.0.1:{bridge.Port}/v1/{new string('a', 64)}/{route}")
        { Version = HttpVersion.Version11, VersionPolicy = HttpVersionPolicy.RequestVersionExact };
        request.Headers.TryAddWithoutValidation("Origin", origin);
        // ResponseContentRead buffers the response before this short-lived client is disposed.
        return client.SendAsync(request, HttpCompletionOption.ResponseContentRead).GetAwaiter().GetResult();
    }
    private static void StructuredFailure()
    {
        using var bridge = new ColabBridge((_, _, _) => throw new ColabProtocolException(426, "incompatible_transport", "Update the notebook."));
        using var response = Request(bridge, "hello");
        Check((int)response.StatusCode == 426, "Compatibility failure lost its HTTP status.");
        using var document = JsonDocument.Parse(response.Content.ReadAsStringAsync().GetAwaiter().GetResult());
        Check(document.RootElement.GetProperty("error").GetProperty("code").GetString() == "incompatible_transport", "Compatibility failure lost its diagnostic code.");
        Check(!document.RootElement.GetProperty("error").GetProperty("retryable").GetBoolean(), "Breaking compatibility was marked transient.");
    }
    private static void OriginBoundary()
    {
        int calls = 0;
        using var bridge = new ColabBridge((_, _, _) => { calls++; return new(Encoding.UTF8.GetBytes("{\"ok\":true}")); });
        using var denied = Request(bridge, "hello", "https://colab.research.google.com.evil.example");
        Check(denied.StatusCode == HttpStatusCode.Forbidden && calls == 0, "An unrelated web origin reached the bridge.");
        Check(!denied.Headers.Contains("Access-Control-Allow-Origin"), "An untrusted origin received CORS permission.");
        using var allowed = Request(bridge, "hello");
        Check(allowed.StatusCode == HttpStatusCode.OK && calls == 1, "The legitimate Colab origin was rejected.");
        Check(allowed.Headers.GetValues("Access-Control-Allow-Origin").Single() == Origin, "CORS reflected the wrong origin.");
    }
    private static void Preflight()
    {
        int calls = 0;
        using var bridge = new ColabBridge((_, _, _) => { calls++; return new(Array.Empty<byte>()); });
        using var response = Request(bridge, "status", method: "OPTIONS");
        Check(response.StatusCode == HttpStatusCode.NoContent && calls == 0, "Preflight executed a command.");
        Check(response.Headers.GetValues("Access-Control-Allow-Private-Network").Single() == "true", "Local-network preflight permission is missing.");
        Check(response.Headers.GetValues("Access-Control-Allow-Methods").Single().Contains("POST", StringComparison.Ordinal), "Status POST is unavailable.");
    }
    private static void OversizedBody()
    {
        int calls = 0;
        using var bridge = new ColabBridge((_, _, _) => { calls++; return new(Array.Empty<byte>()); });
        using var client = new TcpClient(); client.Connect(IPAddress.Loopback, bridge.Port);
        using NetworkStream stream = client.GetStream(); stream.ReadTimeout = 5000; stream.WriteTimeout = 5000;
        string header = $"POST /v1/{new string('a', 64)}/status HTTP/1.1\r\nHost: 127.0.0.1:{bridge.Port}\r\nOrigin: {Origin}\r\nContent-Length: {35 * 1024 * 1024}\r\n\r\n";
        stream.Write(Encoding.ASCII.GetBytes(header));
        using var reader = new StreamReader(stream, Encoding.UTF8);
        string response = reader.ReadToEnd();
        Check(response.StartsWith("HTTP/1.1 413", StringComparison.Ordinal), "Oversized upload was silently disconnected.");
        Check(response.Contains("payload_too_large", StringComparison.Ordinal) && calls == 0, "Oversized upload reached result import.");
    }
}
