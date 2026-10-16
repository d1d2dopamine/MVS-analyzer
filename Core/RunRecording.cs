namespace MvsAnalyzer;

// One operation owns and disposes its session. Helpers may borrow it without disposing.
internal interface IRunRecording : IDisposable
{
    bool EnvironmentChanged { get; }
    bool Try<T>(string key, out T value);
    T Cached<T>(string key, Func<T> calculate);
    void Put<T>(string key, T value);
    T Finish<T>(T value);
}

// BackupRequest remains the existing compatibility descriptor; this is an invocation seam.
internal interface IRunRecordingFactory
{
    IRunRecording Begin(BackupRequest request);
}
