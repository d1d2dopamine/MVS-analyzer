namespace MvsAnalyzer;

internal sealed class ThemedComboBox : ComboBox
{
    public bool DarkMode { get; set; }
    public Color ThemeSurface { get; set; } = Color.White;
    public Color ThemeText { get; set; } = Color.FromArgb(36, 36, 36);
    public Color ThemeAccent { get; set; } = Color.FromArgb(15, 108, 189);
    public ThemedComboBox()
    {
        DrawMode = DrawMode.OwnerDrawFixed; DropDownStyle = ComboBoxStyle.DropDownList; FlatStyle = FlatStyle.Flat; ItemHeight = 22;
    }
    public void ApplyTheme(bool dark, Color surface, Color text, Color accent)
    {
        DarkMode = dark; ThemeSurface = surface; ThemeText = text; ThemeAccent = accent; BackColor = surface; ForeColor = text; Invalidate();
    }
    protected override void OnDrawItem(DrawItemEventArgs e)
    {
        if (e.Index < 0) return;
        bool selected = (e.State & DrawItemState.Selected) != 0;
        using var background = new SolidBrush(selected ? ThemeAccent : ThemeSurface);
        using var foreground = new SolidBrush(selected ? Color.White : ThemeText);
        e.Graphics.FillRectangle(background, e.Bounds);
        e.Graphics.DrawString(GetItemText(Items[e.Index]), Font, foreground, e.Bounds.Left + 5, e.Bounds.Top + 3);
        e.DrawFocusRectangle();
    }
}

internal sealed class ThemedTabControl : TabControl
{
    public bool DarkMode { get; set; }
    public Color ThemeSurface { get; set; } = Color.White;
    public Color ThemeText { get; set; } = Color.FromArgb(36, 36, 36);
    public Color ThemeAccent { get; set; } = Color.FromArgb(15, 108, 189);
    public ThemedTabControl()
    {
        Appearance = TabAppearance.FlatButtons; DrawMode = TabDrawMode.OwnerDrawFixed; SizeMode = TabSizeMode.Fixed; ItemSize = new Size(180, 34); Padding = new Point(16, 6); Multiline = false;
    }
    public void ApplyTheme(bool dark, Color surface, Color text, Color accent)
    {
        DarkMode = dark; ThemeSurface = surface; ThemeText = text; ThemeAccent = accent; BackColor = surface; ForeColor = text; Invalidate();
    }
    protected override void OnDrawItem(DrawItemEventArgs e)
    {
        Rectangle r = GetTabRect(e.Index); bool selected = SelectedIndex == e.Index;
        using var background = new SolidBrush(selected ? ThemeAccent : ThemeSurface);
        using var foreground = new SolidBrush(selected ? Color.White : ThemeText);
        e.Graphics.FillRectangle(background, r);
        TextRenderer.DrawText(e.Graphics, TabPages[e.Index].Text, Font, r, selected ? Color.White : ThemeText, TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter);
    }
}

internal sealed class ThemedNumericUpDown : NumericUpDown
{
    public void ApplyTheme(Color surface, Color text)
    {
        BackColor = surface; ForeColor = text; BorderStyle = BorderStyle.FixedSingle; Invalidate();
    }
}

/// <summary>Panels and grids that paint into a back buffer. Without this every page rebuild
/// repaints control by control, which is the flicker seen when switching sections.</summary>
internal class BufferedPanel : Panel
{
    public BufferedPanel()
    {
        DoubleBuffered = true;
        SetStyle(ControlStyles.OptimizedDoubleBuffer | ControlStyles.AllPaintingInWmPaint, true);
    }
}

internal class BufferedFlowPanel : FlowLayoutPanel
{
    public BufferedFlowPanel()
    {
        DoubleBuffered = true;
        SetStyle(ControlStyles.OptimizedDoubleBuffer | ControlStyles.AllPaintingInWmPaint, true);
    }
}

internal class BufferedGrid : DataGridView
{
    public BufferedGrid()
    {
        DoubleBuffered = true;
        SetStyle(ControlStyles.OptimizedDoubleBuffer | ControlStyles.AllPaintingInWmPaint, true);
    }
}

/// <summary>Freezes painting of a container while its children are rebuilt.</summary>
internal static class Redraw
{
    private const int WM_SETREDRAW = 0x000B;

    [System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Auto)]
    private static extern IntPtr SendMessage(IntPtr window, int message, IntPtr wParam, IntPtr lParam);

    public static void Suspend(Control control)
    {
        if (control.IsHandleCreated) SendMessage(control.Handle, WM_SETREDRAW, IntPtr.Zero, IntPtr.Zero);
    }

    public static void Resume(Control control)
    {
        if (!control.IsHandleCreated) return;
        SendMessage(control.Handle, WM_SETREDRAW, new IntPtr(1), IntPtr.Zero);
        control.Invalidate(true);
    }
}

/// <summary>A card surface with a soft rounded outline instead of the hard 1 px window frame.
/// BorderStyle.FixedSingle produced a grid of boxes; this gives the page some air.</summary>
internal sealed class CardPanel : BufferedPanel
{
    public Color BorderColor { get; set; } = Color.FromArgb(224, 224, 224);
    public int Radius { get; set; } = 8;

    public CardPanel()
    {
        ResizeRedraw = true;
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        if (Width < 4 || Height < 4) return;
        e.Graphics.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
        using var path = Rounded(new Rectangle(0, 0, Width - 1, Height - 1), Radius);
        using var pen = new Pen(BorderColor);
        e.Graphics.DrawPath(pen, path);
    }

    private static System.Drawing.Drawing2D.GraphicsPath Rounded(Rectangle bounds, int radius)
    {
        int diameter = Math.Max(2, radius * 2);
        var path = new System.Drawing.Drawing2D.GraphicsPath();
        path.AddArc(bounds.X, bounds.Y, diameter, diameter, 180, 90);
        path.AddArc(bounds.Right - diameter, bounds.Y, diameter, diameter, 270, 90);
        path.AddArc(bounds.Right - diameter, bounds.Bottom - diameter, diameter, diameter, 0, 90);
        path.AddArc(bounds.X, bounds.Bottom - diameter, diameter, diameter, 90, 90);
        path.CloseFigure();
        return path;
    }
}
