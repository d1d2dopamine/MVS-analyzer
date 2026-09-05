namespace MvsAnalyzer;

internal sealed partial class MainForm
{
    private bool localOperationInProgress;

    private async Task RunLocalTaskAsync(ProgressDialog progress, Func<Task> work)
    {
        if (localOperationInProgress) throw new InvalidOperationException(T("A calculation is already running.", "Расчёт уже выполняется."));
        localOperationInProgress = true;
        try
        {
            progress.ApplyTheme(Surface, TextColor, Secondary, Border, Accent);
            RefreshColabPanel();
            // ShowDialog uses the native modal window lock. Setting this.Enabled = false
            // instead cascades disabled state to every label/input and turns dark text black.
            await progress.RunAsync(this, work);
        }
        finally
        {
            localOperationInProgress = false;
            if (!IsDisposed) { RefreshColabButtons(); RefreshColabPanel(); }
        }
    }
}
