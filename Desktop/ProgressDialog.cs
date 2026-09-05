namespace MvsAnalyzer;

/// <summary>A native modal owner lock leaves managed Enabled/theme colours intact.</summary>
internal sealed class ProgressDialog : Form
{
    private readonly Label action = new() { AutoSize = true, Font = new Font("Segoe UI", 11, FontStyle.Bold) };
    private readonly Label percent = new() { AutoSize = true, Font = new Font("Segoe UI", 20, FontStyle.Bold) };
    private readonly ProgressBar bar = new() { Height = 20, Minimum = 0, Maximum = 100 };
    private readonly Label eta = new() { AutoSize = true };
    private readonly Label details = new() { AutoSize = false, AutoEllipsis = true, Height = 62 };
    private readonly Button cancel = new ThemedButton { Width = 145, Height = 44, Tag = "secondary" };
    private readonly CancellationTokenSource cancellation = new();
    private readonly DateTime started = DateTime.UtcNow;
    private readonly bool russian;
    private bool running, completing;
    public CancellationToken Token => cancellation.Token;

    public ProgressDialog(string title, string cancelText, bool useRussian = false)
    {
        russian = useRussian;
        Text = title; StartPosition = FormStartPosition.CenterParent; AutoScaleMode = AutoScaleMode.Dpi;
        Font = new Font("Segoe UI", 10); ClientSize = new Size(560, 330);
        FormBorderStyle = FormBorderStyle.FixedDialog; MaximizeBox = false; MinimizeBox = false;
        ShowInTaskbar = false; ControlBox = false;
        cancel.Text = cancelText; cancel.Click += (_, _) => RequestCancellation(); CancelButton = cancel;
        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 6, Padding = new Padding(24) };
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        for (int i = 0; i < 6; i++) layout.RowStyles.Add(new RowStyle(i == 4 ? SizeType.Percent : SizeType.AutoSize, i == 4 ? 100 : 0));
        Control[] controls = { action, percent, bar, eta, details, cancel };
        for (int i = 0; i < controls.Length; i++)
        {
            controls[i].Margin = new Padding(0, 0, 0, i == 5 ? 0 : 12);
            controls[i].Dock = i == 5 ? DockStyle.None : DockStyle.Top;
            layout.Controls.Add(controls[i], 0, i);
        }
        cancel.Anchor = AnchorStyles.Right;
        layout.SizeChanged += (_, _) =>
        {
            int width = Math.Max(100, layout.ClientSize.Width - layout.Padding.Horizontal);
            action.MaximumSize = eta.MaximumSize = new Size(width, 0);
        };
        Controls.Add(layout);
    }

    private void RequestCancellation()
    {
        if (cancellation.IsCancellationRequested || completing) return;
        cancel.Enabled = false;
        cancel.Text = russian ? "Остановка…" : "Stopping…";
        cancellation.Cancel();
    }

    public void ApplyTheme(Color background, Color text, Color secondary, Color border, Color accent)
    {
        BackColor = background; ForeColor = text;
        action.ForeColor = percent.ForeColor = text; eta.ForeColor = details.ForeColor = secondary;
        cancel.BackColor = background; cancel.ForeColor = text; cancel.FlatStyle = FlatStyle.Flat;
        cancel.UseVisualStyleBackColor = false; cancel.FlatAppearance.BorderColor = border;
        cancel.FlatAppearance.MouseOverBackColor = Color.FromArgb((background.R * 4 + accent.R) / 5, (background.G * 4 + accent.G) / 5, (background.B * 4 + accent.B) / 5);
        if (cancel is ThemedButton themed) { themed.DisabledTextColor = secondary; themed.DisabledBackColor = background; themed.DisabledBorderColor = border; }
    }

    public Task RunAsync(IWin32Window owner, Func<Task> work)
    {
        if (running) throw new InvalidOperationException("A progress dialog runs only one operation.");
        var completion = new TaskCompletionSource<object?>(TaskCreationOptions.RunContinuationsAsynchronously);
        running = true;
        async void Start(object? sender, EventArgs args)
        {
            try { await work(); completion.TrySetResult(null); }
            catch (Exception error) { completion.TrySetException(error); }
            finally { completing = true; running = false; Close(); }
        }
        Shown += Start;
        try { ShowDialog(owner); }
        finally { Shown -= Start; }
        return completion.Task;
    }

    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        if (running && !completing) { RequestCancellation(); e.Cancel = true; }
        base.OnFormClosing(e);
    }

    public void UpdateProgress(ProgressInfo info)
    {
        // A queued Progress<T> callback can arrive after completion/cancellation.
        if (IsDisposed || Disposing) return;
        double fraction = double.IsFinite(info.Fraction) ? Math.Clamp(info.Fraction, 0, 1) : 0;
        int value = Math.Clamp((int)Math.Round(fraction * 100), 0, 100);
        bar.Value = value; action.Text = info.Action; percent.Text = $"{value}%";
        TimeSpan elapsed = DateTime.UtcNow - started;
        double seconds = fraction > .01 ? Math.Min(TimeSpan.MaxValue.TotalSeconds / 2, elapsed.TotalSeconds * (1 - fraction) / fraction) : 0;
        TimeSpan remaining = TimeSpan.FromSeconds(Math.Max(0, seconds));
        string duration = remaining.TotalHours >= 1 ? remaining.ToString(@"h\:mm\:ss") : remaining.ToString(@"m\:ss");
        eta.Text = fraction > .01 ? (russian ? $"Осталось примерно {duration}" : $"About {duration} remaining")
            : (russian ? "Оценка оставшегося времени…" : "Estimating remaining time…");
        details.Text = info.Details;
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing) cancellation.Dispose();
        base.Dispose(disposing);
    }
}
