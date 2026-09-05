namespace MvsAnalyzer;

/// <summary>Measured, equal-height button rows. Wrap instead of squeezing captions or overlapping.</summary>
internal sealed class ActionButtonPanel : BufferedPanel
{
    private readonly Button[] buttons;
    private readonly int[] requestedWidths;
    private readonly bool stretch;
    private readonly int maxColumns;
    private bool arranging;

    internal ActionButtonPanel(bool stretch, int maxColumns, params Button[] buttons)
    {
        this.buttons = buttons; this.stretch = stretch; this.maxColumns = Math.Max(1, maxColumns);
        requestedWidths = buttons.Select(b => b.Width).ToArray();
        Margin = new Padding(0, 0, 0, 4); AutoSize = false; Height = 44; TabStop = false;
        Controls.AddRange(buttons);
        foreach (Button button in buttons)
        {
            button.TextChanged += (_, _) => PerformLayout();
            button.FontChanged += (_, _) => PerformLayout();
        }
    }

    internal static int CaptionWidth(Button button) => TextRenderer.MeasureText(button.Text, button.Font,
        Size.Empty, TextFormatFlags.SingleLine | TextFormatFlags.NoPrefix).Width + button.Padding.Horizontal +
        (button.Image == null ? 0 : button.Image.Width + 8) + 28;

    internal static int CaptionHeight(Button button, int width, int minimumHeight)
    {
        int imageWidth = button.Image == null ? 0 : button.Image.Width + 8;
        int textWidth = Math.Max(30, width - button.Padding.Horizontal - imageWidth - 20);
        int textHeight = TextRenderer.MeasureText(button.Text, button.Font, new Size(textWidth, int.MaxValue),
            TextFormatFlags.WordBreak | TextFormatFlags.NoPrefix).Height;
        return Math.Max(minimumHeight, Math.Max(textHeight + button.Padding.Vertical + 14, (button.Image?.Height ?? 0) + 14));
    }

    // Also used for the existing page cards, retaining their original control order and callbacks.
    internal static int ArrangeButtons(Control parent, Button[] buttons, int[] widths, int left, int top,
        int availableWidth, bool stretch = false, int maxColumns = int.MaxValue)
    {
        if (buttons.Length == 0) return top;
        int gap = Math.Max(10, (int)Math.Round(10 * parent.DeviceDpi / 96d));
        int minimumHeight = Math.Max(44, (int)Math.Round(44 * parent.DeviceDpi / 96d));
        int available = Math.Max(1, availableWidth);
        int desired = buttons.Select((b, i) => Math.Max(widths[i], CaptionWidth(b))).Max();
        desired = Math.Min(available, desired);
        int columns = Math.Max(1, Math.Min(Math.Min(buttons.Length, maxColumns), (available + gap) / (desired + gap)));
        int width = stretch ? Math.Max(1, (available - (columns - 1) * gap) / columns) : desired;
        int height = buttons.Max(b => CaptionHeight(b, width, minimumHeight));
        for (int i = 0; i < buttons.Length; i++)
        {
            buttons[i].AutoSize = false;
            buttons[i].SetBounds(left + i % columns * (width + gap), top + i / columns * (height + gap), width, height);
        }
        return top + ((buttons.Length + columns - 1) / columns) * (height + gap) - gap;
    }

    protected override void OnLayout(LayoutEventArgs levent)
    {
        base.OnLayout(levent);
        if (arranging || IsDisposed || buttons == null) return;
        arranging = true;
        try
        {
            int[] widths = requestedWidths.Select(w => (int)Math.Round(w * DeviceDpi / 96d)).ToArray();
            Height = ArrangeButtons(this, buttons, widths, 0, 0, ClientSize.Width, stretch, maxColumns);
        }
        finally { arranging = false; }
    }
}
