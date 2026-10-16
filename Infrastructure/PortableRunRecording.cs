namespace MvsAnalyzer;

// Stateless default: ambient nesting, context and restore behavior stay in BackupSession.
internal sealed class PortableRunRecordingFactory : IRunRecordingFactory
{
    internal static readonly PortableRunRecordingFactory Instance = new();
    private PortableRunRecordingFactory() { }
    public IRunRecording Begin(BackupRequest request) => BackupSession.Begin(request);
}
