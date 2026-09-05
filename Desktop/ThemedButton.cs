namespace MvsAnalyzer;

/// <summary>WinForms' disabled flat-button text ignores ForeColor; keep it readable on dark surfaces.</summary>
internal sealed class ThemedButton : Button
{
    public Color DisabledBackColor { get; set; } = SystemColors.Control;
    public Color DisabledBorderColor { get; set; } = SystemColors.ControlDark;
    public Color DisabledTextColor { get; set; } = Color.FromArgb(120, 120, 120);

    public ThemedButton()
    {
        FlatStyle = FlatStyle.Flat; UseVisualStyleBackColor = false;
        SetStyle(ControlStyles.OptimizedDoubleBuffer | ControlStyles.AllPaintingInWmPaint, true);
    }

    protected override void OnEnabledChanged(EventArgs e) { base.OnEnabledChanged(e); Invalidate(); }

    protected override void OnPaint(PaintEventArgs e)
    {
        if (Enabled) { base.OnPaint(e); return; }
        using var brush = new SolidBrush(DisabledBackColor);
        e.Graphics.FillRectangle(brush, ClientRectangle);
        using var border = new Pen(DisabledBorderColor);
        if (Width > 1 && Height > 1) e.Graphics.DrawRectangle(border, 0, 0, Width - 1, Height - 1);
        var textBounds = new Rectangle(Padding.Left + 8, Padding.Top + 4,
            Math.Max(1, ClientSize.Width - Padding.Horizontal - 16), Math.Max(1, ClientSize.Height - Padding.Vertical - 8));
        if (Image != null)
        {
            e.Graphics.DrawImage(Image, Padding.Left + 6, (Height - Image.Height) / 2, Image.Width, Image.Height);
            textBounds.X += Image.Width + 8; textBounds.Width = Math.Max(1, textBounds.Width - Image.Width - 8);
        }
        TextRenderer.DrawText(e.Graphics, Text, Font, textBounds, DisabledTextColor,
            TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter | TextFormatFlags.WordBreak | TextFormatFlags.NoPrefix);
    }
}
