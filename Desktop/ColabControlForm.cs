namespace MvsAnalyzer;

/// <summary>A real modeless top-level window, never a page hosted inside MainForm.</summary>
internal sealed class ColabControlForm : Form
{
    internal readonly BufferedFlowPanel Content = new()
    {
        Dock = DockStyle.Fill, AutoScroll = true, FlowDirection = FlowDirection.TopDown,
        WrapContents = false, Padding = new Padding(16)
    };
    private bool fitting;

    internal ColabControlForm(Font font)
    {
        Text = "MVS Analyzer · Google Colab";
        Font = font; AutoScaleMode = AutoScaleMode.Dpi;
        ClientSize = new Size(620, 650); MinimumSize = new Size(540, 460);
        StartPosition = FormStartPosition.CenterParent; FormBorderStyle = FormBorderStyle.Sizable;
        ShowInTaskbar = true; MinimizeBox = true; MaximizeBox = false;
        try { Icon = Branding.AppIcon; } catch { }
        Controls.Add(Content);
        Content.SizeChanged += (_, _) => FitCards();
        Content.Layout += (_, _) => FitCards();
        DpiChanged += (_, _) => FitCards();
        Shown += (_, _) => FitCards();
    }

    internal void FitCards()
    {
        if (fitting || IsDisposed) return;
        fitting = true;
        try
        {
            int width = Math.Max(100, Content.ClientSize.Width - Content.Padding.Horizontal - SystemInformation.VerticalScrollBarWidth - 2);
            foreach (Control child in Content.Controls)
            {
                child.Width = width;
                if (child is Label label)
                {
                    label.AutoSize = false; label.MaximumSize = Size.Empty;
                    label.Height = TextRenderer.MeasureText(label.Text, label.Font, new Size(width, int.MaxValue),
                        TextFormatFlags.WordBreak | TextFormatFlags.NoPrefix).Height + 8;
                }
            }
        }
        finally { fitting = false; }
    }
}
