// Test-only classification for the owned empty-directory obstruction at MVS_Backups.zip.
// Windows can report access denied where Unix reports an I/O collision. This does
// not change production exception handling or replace post-failure state assertions.
internal static class BackupPublicationFault
{
    internal static void ExpectDirectoryCollision(Action publish, string obstruction)
    {
        if (!Directory.Exists(obstruction)) throw new InvalidOperationException("Owned archive-directory obstruction is missing.");
        try { publish(); }
        catch (Exception error) when (error.GetType() == typeof(IOException) || error.GetType() == typeof(UnauthorizedAccessException))
        {
            if (!Directory.Exists(obstruction)) throw new InvalidOperationException("Owned archive-directory obstruction disappeared.", error);
            return;
        }
        throw new InvalidOperationException("Owned archive-directory obstruction did not reject publication.");
    }

    internal static IEnumerable<(string Name, Action Run)> All => new (string, Action)[] {
        ("Archive fault expectation accepts Unix I/O and Windows access-denied forms", KnownForms),
        ("Archive fault expectation rejects unrelated and derived exceptions", Unrelated),
        ("Archive fault expectation rejects successful publication", Success),
        ("Archive fault expectation requires the owned directory before publication", Missing),
        ("Archive fault expectation requires the owned directory after failure", Removed)
    };
    private static void Isolated(Action<string> test)
    {
        string root = Path.Combine(Path.GetTempPath(), "mvs-publication-fault-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try { test(root); }
        finally { if (Directory.Exists(root)) Directory.Delete(root, true); }
    }
    private static void KnownForms() => Isolated(root => {
        foreach (Exception error in new Exception[] { new IOException("fixture"), new UnauthorizedAccessException("fixture") })
            ExpectDirectoryCollision(() => throw error, root);
    });
    private static void Unrelated() => Isolated(root => {
        foreach (Exception error in new Exception[] { new InvalidDataException("fixture"), new DirectoryNotFoundException("fixture"), new OperationCanceledException("fixture"), new ArgumentException("fixture"), new InvalidOperationException("fixture") })
        {
            Exception? seen = null;
            try { ExpectDirectoryCollision(() => throw error, root); } catch (Exception actual) { seen = actual; }
            if (!ReferenceEquals(seen, error)) throw new Exception("Unexpected fault was swallowed or replaced.");
        }
    });
    private static void Success() => Isolated(root => {
        bool rejected = false;
        try { ExpectDirectoryCollision(() => { }, root); } catch (InvalidOperationException) { rejected = true; }
        if (!rejected) throw new Exception("Success incorrectly satisfied failure expectation.");
    });
    private static void Missing() => Isolated(root => {
        bool invoked = false, rejected = false;
        try { ExpectDirectoryCollision(() => { invoked = true; throw new IOException(); }, Path.Combine(root, "absent")); }
        catch (InvalidOperationException) { rejected = true; }
        if (!rejected || invoked) throw new Exception("Missing obstruction did not fail before action.");
    });
    private static void Removed() => Isolated(root => {
        bool rejected = false;
        try { ExpectDirectoryCollision(() => { Directory.Delete(root); throw new UnauthorizedAccessException(); }, root); }
        catch (InvalidOperationException error) { rejected = error.InnerException is UnauthorizedAccessException; }
        if (!rejected) throw new Exception("Disappeared obstruction was accepted.");
    });
}
