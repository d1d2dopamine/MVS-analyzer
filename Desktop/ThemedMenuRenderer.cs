namespace MvsAnalyzer;

internal sealed class ThemedMenuRenderer : ToolStripProfessionalRenderer
{
    private readonly Color surface, text, secondary, border, hover;
    internal ThemedMenuRenderer(Color surface, Color text, Color secondary, Color border, Color hover)
    { this.surface = surface; this.text = text; this.secondary = secondary; this.border = border; this.hover = hover; RoundedEdges = false; }

    protected override void OnRenderToolStripBackground(ToolStripRenderEventArgs e)
    { using var brush = new SolidBrush(surface); e.Graphics.FillRectangle(brush, e.AffectedBounds); }

    protected override void OnRenderMenuItemBackground(ToolStripItemRenderEventArgs e)
    {
        using var brush = new SolidBrush(e.Item.Selected && e.Item.Enabled ? hover : surface);
        e.Graphics.FillRectangle(brush, new Rectangle(Point.Empty, e.Item.Size));
    }

    protected override void OnRenderItemText(ToolStripItemTextRenderEventArgs e) =>
        TextRenderer.DrawText(e.Graphics, e.Text, e.TextFont, e.TextRectangle, e.Item.Enabled ? text : secondary, e.TextFormat);

    protected override void OnRenderToolStripBorder(ToolStripRenderEventArgs e)
    {
        using var pen = new Pen(border);
        e.Graphics.DrawRectangle(pen, 0, 0, Math.Max(0, e.ToolStrip.Width - 1), Math.Max(0, e.ToolStrip.Height - 1));
    }

    protected override void OnRenderSeparator(ToolStripSeparatorRenderEventArgs e)
    { using var pen = new Pen(border); e.Graphics.DrawLine(pen, 8, e.Item.Height / 2, Math.Max(8, e.Item.Width - 8), e.Item.Height / 2); }
}
