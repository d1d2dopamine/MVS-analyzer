namespace MvsAnalyzer;

internal sealed class ProgressDialog : Form
{
    private readonly Label action = new() { AutoSize = true, Location = new Point(24, 24), Font = new Font("Segoe UI", 11, FontStyle.Bold) };
    private readonly Label percent = new() { AutoSize = true, Font = new Font("Segoe UI", 20, FontStyle.Bold), Location = new Point(24, 55) };
    private readonly ProgressBar bar = new() { Location = new Point(24, 101), Size = new Size(500, 18) };
    private readonly Label eta = new() { AutoSize = true, Location = new Point(24, 137) };
    private readonly Label details = new() { AutoSize = true, Location = new Point(24, 169), ForeColor = Color.DimGray };
    private readonly CancellationTokenSource cancellation = new();
    private readonly DateTime started = DateTime.UtcNow;
    private readonly bool russian;
    public CancellationToken Token => cancellation.Token;
    public ProgressDialog(string title, string cancelText, bool useRussian = false)
    {
        russian = useRussian;
        Text = title; StartPosition = FormStartPosition.CenterParent; AutoScaleMode = AutoScaleMode.Dpi; ClientSize = new Size(550, 260); Font = new Font("Segoe UI", 10);
        FormBorderStyle = FormBorderStyle.FixedDialog; MaximizeBox = false; MinimizeBox = false; ControlBox = false;
        var cancel = new Button { Text = cancelText, Location = new Point(414, 207), Size = new Size(110, 36) }; cancel.Click += (_, _) => cancellation.Cancel();
        Controls.AddRange(new Control[] { action, percent, bar, eta, details, cancel });
    }
    public void UpdateProgress(ProgressInfo info)
    {
        int value = Math.Clamp((int)Math.Round(info.Fraction * 100), 0, 100); bar.Value = value; action.Text = info.Action; percent.Text = $"{value}%";
        TimeSpan elapsed = DateTime.UtcNow - started; double seconds = info.Fraction > .01 ? elapsed.TotalSeconds * (1 - info.Fraction) / info.Fraction : 0;
        eta.Text = info.Fraction > .01 ? (russian ? $"Осталось примерно {TimeSpan.FromSeconds(seconds):m\\:ss}" : $"About {TimeSpan.FromSeconds(seconds):m\\:ss} remaining") : (russian ? "Оценка оставшегося времени…" : "Estimating remaining time…"); details.Text = info.Details;
    }
}
