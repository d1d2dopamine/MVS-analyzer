namespace MvsAnalyzer;

// Fixed-width, explicitly measured cards. No nested AutoSize / Dock.Top feedback loops.
internal sealed partial class MainForm
{
    private sealed record LayoutItem(Control Control, Rectangle Bounds);
    private readonly Dictionary<CardPanel, (int Height, List<LayoutItem> Items)> legacyLayouts = new();
    private readonly HashSet<CardPanel> arrangingLegacy = new();

    private static int WrappedHeight(Control control, int width)
    {
        if (string.IsNullOrEmpty(control.Text)) return control.Font.Height + 2;
        return TextRenderer.MeasureText(control.Text, control.Font, new Size(Math.Max(30, width), int.MaxValue),
            TextFormatFlags.WordBreak | TextFormatFlags.NoPrefix | TextFormatFlags.NoPadding).Height + control.Padding.Vertical + 4;
    }
    private static void FitIntro(Control intro)
    {
        int y = 2;
        foreach (Control item in intro.Controls)
        {
            if (item is not Label label) continue;
            label.AutoSize = false; label.MaximumSize = Size.Empty;
            label.SetBounds(2, y, Math.Max(80, intro.Width - 12), WrappedHeight(label, intro.Width - 12));
            y = label.Bottom + 10;
        }
        intro.Height = Math.Max(60, y);
    }
    private void FitLegacyCard(CardPanel card)
    {
        if (!arrangingLegacy.Add(card)) return;
        try
        {
            if (!legacyLayouts.TryGetValue(card, out var saved))
            {
                saved = (card.Height, card.Controls.Cast<Control>().Select(c => new LayoutItem(c, c.Bounds)).ToList());
                legacyLayouts[card] = saved;
            }
            if (saved.Items.Count == 0) return;
            int naturalWidth = Math.Max(700, saved.Items.Max(x => x.Bounds.Right) + 22);
            double sx = Math.Min(1, Math.Max(200, card.ClientSize.Width - 20) / (double)(naturalWidth - 20));
            var bands = new List<List<LayoutItem>>();
            foreach (LayoutItem item in saved.Items.OrderBy(x => x.Bounds.Top).ThenBy(x => x.Bounds.Left))
            {
                if (bands.Count == 0 || item.Bounds.Top - bands[^1][0].Bounds.Top > 9) bands.Add(new List<LayoutItem>());
                bands[^1].Add(item);
            }
            int previousBottom = 0, previousOriginalBottom = 0;
            foreach (var band in bands)
            {
                var items = band.OrderBy(x => x.Bounds.Left).ToArray();
                int originalTop = band.Min(x => x.Bounds.Top);
                int top = Math.Max(originalTop, previousBottom + Math.Max(8, originalTop - previousOriginalBottom));
                int bandBottom = top;
                if (items.All(x => x.Control is Button && !x.Control.IsDisposed))
                {
                    // Equal heights and measured caption widths; wrap an action row as a unit.
                    var buttons = items.Select(x => (Button)x.Control).ToArray();
                    bandBottom = ActionButtonPanel.ArrangeButtons(card, buttons, items.Select(x => x.Bounds.Width).ToArray(),
                        20, top, Math.Max(1, card.ClientSize.Width - 40));
                    previousBottom = bandBottom;
                    previousOriginalBottom = band.Max(x => x.Bounds.Bottom);
                    continue;
                }
                for (int i = 0; i < items.Length; i++)
                {
                    LayoutItem item = items[i]; Control child = item.Control;
                    if (child.IsDisposed || child.Dock != DockStyle.None) continue;
                    int left = 20 + (int)Math.Round((item.Bounds.Left - 20) * sx);
                    int next = i + 1 < items.Length ? 20 + (int)Math.Round((items[i + 1].Bounds.Left - 20) * sx) - 12 : card.ClientSize.Width - 20;
                    int width = Math.Max(32, Math.Min((int)Math.Round(item.Bounds.Width * sx), next - left));
                    int height = item.Bounds.Height;
                    if (child is Label label)
                    {
                        label.AutoSize = false; label.MaximumSize = Size.Empty;
                        width = Math.Max(32, next - left); height = WrappedHeight(label, width);
                    }
                    else if (child is CheckBox check)
                    { check.AutoSize = false; width = Math.Max(32, next - left); height = Math.Max(28, WrappedHeight(check, width - 30) + 4); }
                    else if (child is Button button)
                    {
                        width = Math.Max(90, width); height = ActionButtonPanel.CaptionHeight(button, width, (int)Math.Round(44 * card.DeviceDpi / 96d));
                    }
                    else if (child is DataGridView || child is TableLayoutPanel || child is TabControl)
                        width = Math.Max(120, card.ClientSize.Width - left - 20);
                    child.SetBounds(left, top, Math.Min(width, card.ClientSize.Width - left - 12), height);
                    bandBottom = Math.Max(bandBottom, child.Bottom);
                }
                previousBottom = bandBottom;
                previousOriginalBottom = band.Max(x => x.Bounds.Bottom);
            }
            card.Height = Math.Max(saved.Height, previousBottom + 22);
        }
        finally { arrangingLegacy.Remove(card); }
    }

    private Panel FlowCard(string title, string explanation, params Control[] body)
    {
        var card = new CardPanel { Name = "content-card", Tag = "stack-card", Width = ContentWidth,
            AutoSize = false, Height = 150, BackColor = Surface, ForeColor = TextColor, BorderColor = Border,
            Padding = new Padding(20), Margin = new Padding(0, 0, 0, 16) };
        var heading = new Label { Text = title, Font = new Font("Segoe UI", 12, FontStyle.Bold), AutoSize = false, Margin = new Padding(0, 0, 0, 10) };
        var description = new Label { Text = explanation, AutoSize = false, ForeColor = Secondary, Margin = new Padding(0, 0, 0, 16) };
        card.Controls.Add(heading);
        if (explanation.Length != 0) card.Controls.Add(description); else description.Dispose();
        card.Controls.AddRange(body);
        bool arranging = false;
        void Arrange()
        {
            if (arranging || card.IsDisposed) return;
            arranging = true;
            try
            {
                int width = Math.Max(160, card.ClientSize.Width - 40), y = 20;
                foreach (Control child in card.Controls)
                {
                    if (!child.Visible && card.Visible) continue;
                    child.Dock = DockStyle.None;
                    int height = child.Height;
                    if (child is Label label)
                    { label.AutoSize = false; label.MaximumSize = Size.Empty; height = WrappedHeight(label, width); child.Width = width; }
                    else if (child is Button button)
                    { child.Width = Math.Min(Math.Max(210, ActionButtonPanel.CaptionWidth(button)), width); height = ActionButtonPanel.CaptionHeight(button, child.Width, (int)Math.Round(44 * card.DeviceDpi / 96d)); }
                    else if (child is CheckBox check)
                    { check.AutoSize = false; child.Width = width; height = Math.Max(28, WrappedHeight(check, width - 30) + 4); }
                    else { child.Width = width; child.PerformLayout(); height = child.Height; }
                    y += child.Margin.Top;
                    child.Location = new Point(20, y); child.Height = Math.Max(20, height);
                    y = child.Bottom + Math.Max(10, child.Margin.Bottom);
                }
                card.Height = Math.Max(100, y + 10);
            }
            finally { arranging = false; }
        }
        card.SizeChanged += (_, _) => Arrange(); card.VisibleChanged += (_, _) => Arrange();
        foreach (Control child in card.Controls)
        { child.TextChanged += (_, _) => Arrange(); child.FontChanged += (_, _) => Arrange(); child.VisibleChanged += (_, _) => Arrange(); child.SizeChanged += (_, _) => Arrange(); }
        Arrange(); return card;
    }
    private Panel FormRows(params (string Label, Control Input)[] rows)
    {
        var panel = new Panel { Width = ContentWidth - 40, AutoSize = false, BackColor = Surface, Margin = new Padding(0, 0, 0, 8) };
        var labels = new List<Label>();
        foreach (var row in rows)
        {
            var label = new Label { Text = row.Label, AutoSize = false, TextAlign = ContentAlignment.MiddleLeft };
            panel.Controls.Add(label); panel.Controls.Add(row.Input); labels.Add(label);
        }
        bool busy = false;
        void Arrange()
        {
            if (busy) return; busy = true;
            try
            {
                bool vertical = panel.Width < 510;
                int labelWidth = vertical ? panel.Width : (int)(panel.Width * .51), y = 0;
                for (int i = 0; i < rows.Length; i++)
                {
                    Label label = labels[i]; Control input = rows[i].Input;
                    int labelHeight = WrappedHeight(label, labelWidth - 16), inputHeight = Math.Max(30, input.PreferredSize.Height);
                    label.SetBounds(0, y + 4, labelWidth - 16, Math.Max(28, labelHeight));
                    input.SetBounds(vertical ? 0 : labelWidth, vertical ? label.Bottom + 4 : y + 4,
                        Math.Max(100, vertical ? panel.Width : panel.Width - labelWidth), inputHeight);
                    y = Math.Max(label.Bottom, input.Bottom) + 12;
                }
                panel.Height = Math.Max(30, y);
            }
            finally { busy = false; }
        }
        panel.SizeChanged += (_, _) => Arrange(); panel.Layout += (_, _) => Arrange(); Arrange(); return panel;
    }
    private void AddAdditionalMethodsLink(FlowLayoutPanel page)
    {
        var row = new Panel { Width = ContentWidth, Height = 50, Margin = new Padding(0, 0, 0, 12) };
        var open = Button(T("Additional methods…", "Дополнительные методы…"), false, 285);
        open.Location = Point.Empty; open.Height = 44;
        open.AccessibleDescription = T("Optional variance components, repeated-measurement MELSM and estimation studies.", "Необязательные компоненты дисперсии, MELSM для повторных измерений и исследование точности оценок.");
        open.Click += (_, _) => Navigate("advanced"); row.Controls.Add(open); page.Controls.Add(row);
    }
}
