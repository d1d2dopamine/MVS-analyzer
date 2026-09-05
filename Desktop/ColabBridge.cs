using System.Net;
using System.Net.Sockets;
using System.Text;

namespace MvsAnalyzer;

internal sealed record ColabHttpReply(byte[] Body, string ContentType = "application/json", int Status = 200);

/// <summary>Opt-in loopback transport. No public listener, shell endpoint, Google cookies or account tokens.</summary>
internal sealed class ColabBridge : IDisposable
{
    private readonly TcpListener listener;
    private readonly CancellationTokenSource cancellation = new();
    private readonly SemaphoreSlim clients = new(4);
    private readonly Func<string, string, byte[], ColabHttpReply> dispatch;
    public int Port { get; }
    public ColabBridge(Func<string, string, byte[], ColabHttpReply> handler)
    {
        dispatch = handler; listener = new TcpListener(IPAddress.Loopback, 0); listener.Start(8);
        Port = ((IPEndPoint)listener.LocalEndpoint).Port; _ = ListenAsync();
    }
    internal static bool AllowedOrigin(string value)
    {
        if (!Uri.TryCreate(value, UriKind.Absolute, out Uri? uri) || uri.Scheme != "https" || !uri.IsDefaultPort || uri.UserInfo.Length != 0 || uri.AbsolutePath != "/") return false;
        return uri.Host == "colab.research.google.com" || uri.Host.EndsWith(".googleusercontent.com", StringComparison.OrdinalIgnoreCase);
    }
    private async Task ListenAsync()
    {
        try
        {
            while (!cancellation.IsCancellationRequested)
            {
                TcpClient client = await listener.AcceptTcpClientAsync(cancellation.Token);
                if (!await clients.WaitAsync(0, cancellation.Token)) { client.Dispose(); continue; }
                _ = ServeAsync(client);
            }
        }
        catch (Exception error) when (error is OperationCanceledException or SocketException or ObjectDisposedException) { }
    }
    private async Task ServeAsync(TcpClient client)
    {
        using (client)
        using (var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellation.Token))
        {
            timeout.CancelAfter(TimeSpan.FromSeconds(20));
            try
            {
                NetworkStream stream = client.GetStream();
                using var header = new MemoryStream(); byte[] one = new byte[1]; int last = 0;
                while (header.Length < 16384)
                {
                    if (await stream.ReadAsync(one, timeout.Token) != 1) return;
                    header.WriteByte(one[0]); last = (last << 8) | one[0];
                    if (last == 0x0d0a0d0a) break;
                }
                if (last != 0x0d0a0d0a) return;
                string[] lines = Encoding.ASCII.GetString(header.ToArray()).Split("\r\n");
                string[] request = lines[0].Split(' ');
                if (request.Length != 3 || request[2] != "HTTP/1.1") return;
                var fields = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
                foreach (string line in lines.Skip(1).Where(s => s.Length > 0))
                {
                    int colon = line.IndexOf(':'); if (colon <= 0 || !fields.TryAdd(line[..colon].Trim(), line[(colon + 1)..].Trim())) return;
                }
                if (fields.GetValueOrDefault("Host") != "127.0.0.1:" + Port || fields.ContainsKey("Transfer-Encoding")) return;
                string origin = fields.GetValueOrDefault("Origin", "");
                if (!AllowedOrigin(origin)) { await Respond(stream, new(Array.Empty<byte>(), Status: 403), "", timeout.Token); return; }
                if (request[0] == "OPTIONS")
                {
                    await Respond(stream, new(Array.Empty<byte>(), Status: 204), origin, timeout.Token); return;
                }
                string[] route = request[1].Split('/', StringSplitOptions.RemoveEmptyEntries);
                if (route.Length != 3 || route[0] != "v1" || !ColabSessionStore.HexKey(route[1]) || !new[] { "hello", "job", "status", "request" }.Contains(route[2]))
                { await Respond(stream, Error(404, "unknown_route", "This MVS connection does not support the requested endpoint."), origin, timeout.Token); return; }
                byte[] body = Array.Empty<byte>();
                if (request[0] == "POST")
                {
                    if (!int.TryParse(fields.GetValueOrDefault("Content-Length"), out int length) || length < 0)
                    { await Respond(stream, Error(400, "invalid_length", "Invalid request size."), origin, timeout.Token); return; }
                    if (length > 34 * 1024 * 1024)
                    { await Respond(stream, Error(413, "payload_too_large", "The status bundle exceeds the transfer limit. Download the result ZIP and import it manually."), origin, timeout.Token); return; }
                    body = new byte[length]; await stream.ReadExactlyAsync(body, timeout.Token);
                }
                else if (request[0] != "GET") return;
                if ((route[2] == "status") != (request[0] == "POST")) return;
                ColabHttpReply reply;
                try { reply = dispatch(route[1], route[2], body); }
                catch (ColabProtocolException error) { reply = Error(error.HttpStatus, error.Code, error.Message); }
                catch (Exception error) when (error is IOException or ArgumentException or System.Text.Json.JsonException or FormatException or InvalidOperationException or KeyNotFoundException or InvalidDataException)
                { reply = Error(400, "invalid_payload", "MVS rejected the status or result validation. Check matching data/settings, hashes and notebook format; reconnecting cannot fix a corrupt result."); }
                await Respond(stream, reply, origin, timeout.Token);
            }
            catch (Exception error) when (error is IOException or OperationCanceledException or ObjectDisposedException or SocketException) { }
            finally { clients.Release(); }
        }
    }
    internal static ColabHttpReply Error(int status, string code, string message, bool retryable = false) =>
        new(Encoding.UTF8.GetBytes(System.Text.Json.JsonSerializer.Serialize(new { error = new { code, message, retryable } })), Status: status);

    private static async Task Respond(NetworkStream stream, ColabHttpReply reply, string origin, CancellationToken token)
    {
        string status = reply.Status switch { 200 => "OK", 204 => "No Content", 403 => "Forbidden", 404 => "Not Found", 409 => "Conflict", 413 => "Content Too Large", 426 => "Upgrade Required", _ => "Bad Request" };
        string headers = $"HTTP/1.1 {reply.Status} {status}\r\nContent-Type: {reply.ContentType}\r\nContent-Length: {reply.Body.Length}\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\nConnection: close\r\n";
        if (origin.Length > 0) headers += $"Access-Control-Allow-Origin: {origin}\r\nVary: Origin\r\nAccess-Control-Allow-Methods: GET, POST, OPTIONS\r\nAccess-Control-Allow-Headers: Content-Type\r\nAccess-Control-Allow-Private-Network: true\r\n";
        await stream.WriteAsync(Encoding.ASCII.GetBytes(headers + "\r\n"), token);
        if (reply.Body.Length > 0) await stream.WriteAsync(reply.Body, token);
    }
    public void Dispose() { cancellation.Cancel(); listener.Stop(); }
}
