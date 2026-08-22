using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Globalization;
using System.Text;
using System.Text.Json;

namespace MvsAnalyzer;

internal static class FigureGenerator
{
    private static readonly Color Blue = Color.FromArgb(15, 108, 189);
    private static readonly Color Green = Color.FromArgb(16, 124, 16);
    private static readonly Color Orange = Color.FromArgb(202, 80, 16);
    private static readonly Color Grid = Color.FromArgb(220, 220, 220);
    // One shared palette so group 3+ is no longer painted like group 2.
    private static readonly Color[] Palette = { Blue, Orange, Green, Color.FromArgb(135, 100, 184), Color.FromArgb(3, 131, 135) };
    private static readonly string[] SvgPalette = { "#0f6cbd", "#ca5010", "#107c10", "#8764b8", "#038387" };
    private static Color GroupColor(int index) => Palette[index % Palette.Length];
    private static int GroupIndex(AnalysisData data, string group) { for (int i = 0; i < data.GroupNames.Length; i++) if (string.Equals(data.GroupNames[i], group, StringComparison.OrdinalIgnoreCase)) return i; return 0; }
    // The unit comes from the file instead of the hard-coded "ms".
    private static string UnitSuffix(AnalysisData data) => string.IsNullOrWhiteSpace(data.Unit) ? "" : " " + data.Unit;

    public static List<string> Generate(AnalysisData data, List<ResultRow> results, AppSettings settings, string runId, string? destinationFolder = null)
    {
        string folder = destinationFolder ?? settings.FigureOutputFolder;
        if (string.IsNullOrWhiteSpace(folder)) throw new InvalidOperationException("Figure output folder was not selected.");
        Directory.CreateDirectory(folder);
        string[] templates = settings.FigureTemplates.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        // A run with figures enabled must never end with zero images and no explanation.
        if (templates.Length == 0) templates = new[] { "value_distribution", "mvs_score", "fpr_power", "group_comparison" };
        var files = new List<string>();
        if (settings.FigureExportMode is "separate" or "both")
            foreach (string template in templates) files.Add(SaveOne(template, data, results, settings, runId, folder));
        if (settings.FigureExportMode is "dashboard" or "both") files.Add(SaveDashboard(data, results, settings, runId, folder));
        return files;
    }

    private static string SaveOne(string template, AnalysisData data, List<ResultRow> results, AppSettings settings, string runId, string folder)
    {
        string safe = template.Replace(' ', '_'); string path = Path.Combine(folder, $"{runId}_{safe}.{settings.FigureFormat}");
        if (settings.FigureFormat == "svg") File.WriteAllText(path, BuildSvg(template, data, results), new UTF8Encoding(false));
        else
        {
            using var bitmap = new Bitmap(1400, 900); using Graphics g = Graphics.FromImage(bitmap); Prepare(g, bitmap.Size);
            DrawTemplate(g, new Rectangle(70, 70, 1260, 750), template, data, results); bitmap.Save(path, ImageFormat.Png);
        }
        return path;
    }

    private static string SaveDashboard(AnalysisData data, List<ResultRow> results, AppSettings settings, string runId, string folder)
    {
        string path = Path.Combine(folder, $"{runId}_dashboard.{settings.FigureFormat}");
        if (settings.FigureFormat == "svg") File.WriteAllText(path, BuildDashboardSvg(data, results), new UTF8Encoding(false));
        else
        {
            using var bitmap = new Bitmap(1800, 1200); using Graphics g = Graphics.FromImage(bitmap); Prepare(g, bitmap.Size);
            using var title = new Font("Segoe UI", 24, FontStyle.Bold); g.DrawString("MVS analysis dashboard", title, Brushes.Black, 55, 25);
            DrawTemplate(g, new Rectangle(60, 100, 800, 480), "mvs_score", data, results);
            DrawTemplate(g, new Rectangle(940, 100, 800, 480), "fpr_power", data, results);
            DrawTemplate(g, new Rectangle(60, 650, 800, 450), "value_distribution", data, results);
            DrawTemplate(g, new Rectangle(940, 650, 800, 450), "group_comparison", data, results);
            bitmap.Save(path, ImageFormat.Png);
        }
        return path;
    }

    private static void Prepare(Graphics g, Size size)
    {
        g.SmoothingMode = SmoothingMode.AntiAlias; g.Clear(Color.White); g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;
    }
    private static void DrawTemplate(Graphics g, Rectangle area, string template, AnalysisData data, List<ResultRow> results)
    {
        using var border = new Pen(Color.FromArgb(210, 210, 210)); g.DrawRectangle(border, area);
        Rectangle plot = new(area.Left + 70, area.Top + 65, area.Width - 105, area.Height - 125);
        if (IsBuiltIn(template)) { DrawBuiltIn(g, plot, template, data, results); return; }
        // A plugin template is drawn from its own geometry now. Redirecting it to a
        // built-in chart made every plugin produce a duplicate of an existing figure.
        FigureSpec? spec = LoadSpec(template);
        if (spec == null) { DrawMissing(g, plot, template); return; }
        DrawSpec(g, plot, spec, data, results);
    }

    internal static bool IsBuiltIn(string id) => id is "value_distribution" or "mvs_score" or "fpr_power" or "group_comparison" or "sequence_course" or "data_quality";

    private static void DrawBuiltIn(Graphics g, Rectangle plot, string template, AnalysisData data, List<ResultRow> results)
    {
        switch (template)
        {
            case "fpr_power": DrawFprPower(g, plot, results); break;
            case "value_distribution": DrawHistogram(g, plot, data); break;
            case "group_comparison": DrawGroupComparison(g, plot, data); break;
            case "sequence_course": DrawTrialTimeCourse(g, plot, data); break;
            case "data_quality": DrawDataQuality(g, plot, data); break;
            default: DrawScores(g, plot, results); break;
        }
    }
    private static void Title(Graphics g, Rectangle plot, string text)
    {
        using var font = new Font("Segoe UI", 16, FontStyle.Bold); g.DrawString(text, font, Brushes.Black, plot.Left, plot.Top - 45);
    }
    private static void Axes(Graphics g, Rectangle p)
    {
        using var axis = new Pen(Color.FromArgb(80, 80, 80), 2); g.DrawLine(axis, p.Left, p.Bottom, p.Right, p.Bottom); g.DrawLine(axis, p.Left, p.Top, p.Left, p.Bottom);
    }
    private static void DrawScores(Graphics g, Rectangle p, List<ResultRow> results)
    {
        Title(g, p, "MVS Score — all metrics"); Axes(g, p); results = results.Where(x => double.IsFinite(x.Score)).ToList(); if (results.Count == 0) return; double max = Math.Max(100, results.Max(x => x.Score)); int slot = Math.Max(20, p.Width / results.Count);
        using var label = new Font("Segoe UI", 9); using var value = new Font("Segoe UI", 9, FontStyle.Bold);
        for (int i = 0; i < results.Count; i++)
        {
            ResultRow r = results[i]; int h = (int)(p.Height * r.Score / max); int x = p.Left + i * slot + 7; int w = Math.Max(12, slot - 18);
            using var brush = new SolidBrush(r.Candidate ? Green : Blue); g.FillRectangle(brush, x, p.Bottom - h, w, h); g.DrawString(r.Score.ToString("0.0"), value, Brushes.Black, x, p.Bottom - h - 20);
            g.TranslateTransform(x + w / 2, p.Bottom + 8); g.RotateTransform(45); g.DrawString(r.Metric, label, Brushes.Black, 0, 0); g.ResetTransform();
        }
    }
    private static void DrawFprPower(Graphics g, Rectangle p, List<ResultRow> results)
    {
        Title(g, p, "Calibrated FPR vs power"); Axes(g, p); results = results.Where(x => double.IsFinite(x.Fpr) && double.IsFinite(x.Power)).ToList(); if (results.Count == 0) return;
        using var gridPen = new Pen(Grid); using var leader = new Pen(Color.FromArgb(170, 170, 170)); using var label = new Font("Segoe UI", 9);
        double maxFpr = Math.Max(.10, results.Max(x => x.Fpr) * 1.15);
        for (int i = 0; i <= 5; i++) { int y = p.Bottom - i * p.Height / 5; g.DrawLine(gridPen, p.Left, y, p.Right, y); g.DrawString((i / 5d).ToString("0.0", CultureInfo.InvariantCulture), label, Brushes.Black, p.Left - 38, y - 7); }
        // The X axis had no ticks at all, so every point looked like it had the same FPR.
        for (int i = 0; i <= 5; i++)
        {
            int x = p.Left + i * p.Width / 5; g.DrawLine(gridPen, x, p.Top, x, p.Bottom);
            string text = (maxFpr * i / 5).ToString("0.000", CultureInfo.InvariantCulture); SizeF size = g.MeasureString(text, label);
            g.DrawString(text, label, Brushes.Black, x - size.Width / 2, p.Bottom + 8);
        }
        var placed = new List<RectangleF>();
        foreach (ResultRow r in results.OrderByDescending(x => x.Power))
        {
            int x = p.Left + (int)(p.Width * r.Fpr / maxFpr); int y = p.Bottom - (int)(p.Height * r.Power);
            using var brush = new SolidBrush(r.Candidate ? Green : Orange); g.FillEllipse(brush, x - 7, y - 7, 14, 14);
            // Clustered metrics used to print their names on top of each other.
            SizeF size = g.MeasureString(r.Metric, label); float lx = x + 11, ly = y - size.Height / 2;
            var box = new RectangleF(lx, ly, size.Width, size.Height);
            for (int guard = 0; guard < 24 && placed.Any(b => b.IntersectsWith(box)); guard++) { ly += size.Height + 1; box = new RectangleF(lx, ly, size.Width, size.Height); }
            placed.Add(box);
            if (Math.Abs(ly - (y - size.Height / 2)) > 2) g.DrawLine(leader, x + 7, y, lx - 2, ly + size.Height / 2);
            g.DrawString(r.Metric, label, Brushes.Black, lx, ly);
        }
        g.DrawString("FPR", label, Brushes.Black, p.Right - 25, p.Bottom + 30); g.DrawString("Power", label, Brushes.Black, p.Left - 52, p.Top - 22);
    }
    private static void DrawHistogram(Graphics g, Rectangle p, AnalysisData data)
    {
        Title(g, p, "Measurement distribution"); Axes(g, p); double min = data.Observations.Min(x => x.Value), max = data.Observations.Max(x => x.Value); int bins = 24;
        string[] groups = data.GroupNames; int[][] counts = groups.Select(_ => new int[bins]).ToArray();
        for (int k = 0; k < groups.Length; k++) foreach (var o in data.Observations.Where(x => string.Equals(x.Group, groups[k], StringComparison.OrdinalIgnoreCase))) { int b = Math.Clamp((int)((o.Value - min) / Math.Max(1, max - min) * bins), 0, bins - 1); counts[k][b]++; }
        int maxCount = Math.Max(1, counts.SelectMany(x => x).Max()); float bw = p.Width / (float)bins;
        for (int b = 0; b < bins; b++) for (int k = 0; k < groups.Length; k++) { float h = p.Height * counts[k][b] / (float)maxCount; using var brush = new SolidBrush(Color.FromArgb(140, GroupColor(k))); g.FillRectangle(brush, p.Left + b * bw, p.Bottom - h, bw - 1, h); }
        using var font = new Font("Segoe UI", 9); string unit = UnitSuffix(data);
        g.DrawString($"{min:0.##}{unit}", font, Brushes.Black, p.Left, p.Bottom + 18); g.DrawString($"{max:0.##}{unit}", font, Brushes.Black, p.Right - 70, p.Bottom + 18);
        for (int k = 0; k < groups.Length; k++) { using var legend = new SolidBrush(GroupColor(k)); g.FillRectangle(legend, p.Right - 130, p.Top + 4 + k * 18, 12, 12); g.DrawString(groups[k], font, Brushes.Black, p.Right - 114, p.Top + 2 + k * 18); }
    }
    private static void DrawGroupComparison(Graphics g, Rectangle p, AnalysisData data)
    {
        Title(g, p, "Entity median value by group"); Axes(g, p); double[] medians = data.GroupNames.Select(group => Median(data.Entities.Where(x => string.Equals(x.Group, group, StringComparison.OrdinalIgnoreCase)).Select(x => x.Metrics[0]).ToArray())).ToArray(); double max = Math.Max(1, medians.Max() * 1.2); int slot = p.Width / medians.Length; Color[] colors = { Blue, Orange, Green, Color.MediumPurple, Color.Teal };
        using var font = new Font("Segoe UI", 9);
        // Bars without a scale cannot be read; the value axis is drawn now.
        using (var gridPen = new Pen(Grid)) for (int i = 0; i <= 4; i++) { int y = p.Bottom - i * p.Height / 4; g.DrawLine(gridPen, p.Left, y, p.Right, y); g.DrawString((max * i / 4).ToString("0.#", CultureInfo.InvariantCulture), font, Brushes.Black, p.Left - 52, y - 7); }
        g.DrawString(data.MeasurementName + UnitSuffix(data), font, Brushes.Black, p.Left - 52, p.Top - 22);
        for (int i = 0; i < medians.Length; i++) { int width = Math.Min(110, slot - 12), x = p.Left + i * slot + (slot - width) / 2, h = (int)(p.Height * medians[i] / max); using var brush = new SolidBrush(colors[i % colors.Length]); g.FillRectangle(brush, x, p.Bottom - h, width, h); g.DrawString($"{medians[i]:0.##}", font, Brushes.Black, x, p.Bottom - h - 20); g.DrawString(data.GroupNames[i], font, Brushes.Black, x, p.Bottom + 16); }
    }
    private static void DrawTrialTimeCourse(Graphics g, Rectangle p, AnalysisData data)
    {
        Title(g, p, "Measurement across sequence"); Axes(g, p); int maxTrial = Math.Max(1, data.Observations.Max(x => x.Sequence)); int bins = Math.Min(30, maxTrial); double min = data.Observations.Min(x => x.Value), max = data.Observations.Max(x => x.Value);
        using var label = new Font("Segoe UI", 9);
        for (int groupIndex = 0; groupIndex < data.GroupNames.Length; groupIndex++)
        {
            var points = new List<PointF>();
            for (int b = 0; b < bins; b++)
            {
                int start = b * maxTrial / bins + 1, end = (b + 1) * maxTrial / bins;
                double[] values = data.Observations.Where(o => o.Group == data.GroupNames[groupIndex] && o.Sequence >= start && o.Sequence <= end).Select(o => o.Value).ToArray(); if (values.Length == 0) continue;
                float x = p.Left + (b + .5f) * p.Width / bins; float y = p.Bottom - (float)((values.Average() - min) / Math.Max(1, max - min) * p.Height); points.Add(new PointF(x, y));
            }
            using var pen = new Pen(GroupColor(groupIndex), 3); if (points.Count > 1) g.DrawLines(pen, points.ToArray()); foreach (PointF point in points) using (var brush = new SolidBrush(GroupColor(groupIndex))) g.FillEllipse(brush, point.X - 3, point.Y - 3, 6, 6);
            using (var legend = new SolidBrush(GroupColor(groupIndex))) g.DrawString(data.GroupNames[groupIndex], label, legend, p.Right - 100, p.Top + groupIndex * 20);
        }
        g.DrawString("Sequence", label, Brushes.Black, p.Right - 60, p.Bottom + 20); g.DrawString(data.MeasurementName + UnitSuffix(data), label, Brushes.Black, p.Left - 28, p.Top - 18);
    }
    private static void DrawDataQuality(Graphics g, Rectangle p, AnalysisData data)
    {
        Title(g, p, "Measurements per entity"); Axes(g, p);
        EntityResult[] people = data.Entities.ToArray(); if (people.Length == 0) return;
        using var font = new Font("Segoe UI", 9); using var gridPen = new Pen(Grid);
        int low = people.Min(x => x.Measurements), high = people.Max(x => x.Measurements);
        int below = people.Count(x => x.Measurements < data.MinMeasurementsApplied);
        if (low == high)
        {
            // 90 identical bars carried one fact. One sentence carries it better.
            using var big = new Font("Segoe UI", 20, FontStyle.Bold);
            g.DrawString($"{people.Length} entities · {low} measurements each", big, Brushes.Black, p.Left + 20, p.Top + p.Height / 2 - 30);
            g.DrawString($"Applied threshold: {data.MinMeasurementsApplied} · below threshold: {below}", font, Brushes.Black, p.Left + 20, p.Top + p.Height / 2 + 12);
            return;
        }
        int bins = Math.Min(20, Math.Max(4, high - low + 1)); var counts = new int[bins];
        foreach (EntityResult person in people) counts[Math.Clamp((int)((person.Measurements - low) / (double)(high - low) * (bins - 1)), 0, bins - 1)]++;
        int peak = Math.Max(1, counts.Max()); float bw = p.Width / (float)bins;
        for (int i = 0; i <= 4; i++) { int y = p.Bottom - i * p.Height / 4; g.DrawLine(gridPen, p.Left, y, p.Right, y); g.DrawString((peak * i / 4d).ToString("0", CultureInfo.InvariantCulture), font, Brushes.Black, p.Left - 38, y - 7); }
        for (int b = 0; b < bins; b++)
        {
            float h = p.Height * counts[b] / (float)peak; if (h <= 0) continue;
            using var brush = new SolidBrush(Blue); g.FillRectangle(brush, p.Left + b * bw + 1, p.Bottom - h, Math.Max(1, bw - 2), h);
        }
        if (data.MinMeasurementsApplied > low && data.MinMeasurementsApplied < high)
        {
            float tx = p.Left + (float)((data.MinMeasurementsApplied - low) / (double)(high - low)) * p.Width;
            using var threshold = new Pen(Color.FromArgb(202, 80, 16), 2) { DashStyle = DashStyle.Dash };
            g.DrawLine(threshold, tx, p.Top, tx, p.Bottom); g.DrawString("min", font, Brushes.Black, tx + 4, p.Top);
        }
        g.DrawString(low.ToString(CultureInfo.InvariantCulture), font, Brushes.Black, p.Left, p.Bottom + 8);
        g.DrawString(high.ToString(CultureInfo.InvariantCulture), font, Brushes.Black, p.Right - 30, p.Bottom + 8);
        g.DrawString($"N = {people.Length} · min {low} · max {high} · below threshold ({data.MinMeasurementsApplied}): {below}", font, Brushes.Black, p.Left, p.Bottom + 34);
        g.DrawString("Entities", font, Brushes.Black, p.Left - 52, p.Top - 22); g.DrawString("Measurements per entity", font, Brushes.Black, p.Right - 160, p.Bottom + 34);
    }
    private static double Median(double[] x) { Array.Sort(x); return x.Length % 2 == 1 ? x[x.Length / 2] : (x[x.Length / 2 - 1] + x[x.Length / 2]) / 2; }

    private static string BuildSvg(string template, AnalysisData data, List<ResultRow> results)
    {
        if (!IsBuiltIn(template))
        {
            FigureSpec? mapped = LoadSpec(template);
            if (mapped == null) return SvgStart(1400, 900).Append("<rect width='100%' height='100%' fill='white'/><text x='80' y='120' font-size='26' font-family='Segoe UI' fill='#b0421b'>Template not found: ").Append(Escape(template)).Append("</text></svg>").ToString();
            // SVG export still uses the closest built-in shape; PNG uses the real geometry.
            template = MapToBuiltIn(mapped);
        }
        var s = SvgStart(1400, 900); s.Append("<rect width='100%' height='100%' fill='white'/>");
        if (template == "fpr_power") SvgScatter(s, results, 100, 120, 1200, 650); else if (template == "value_distribution") SvgHistogram(s, data, 100, 120, 1200, 650); else if (template == "sequence_course") SvgTrialTimeCourse(s, data, 100, 120, 1200, 650); else if (template == "data_quality") SvgDataQuality(s, data, 100, 120, 1200, 650); else if (template == "group_comparison") SvgGroupComparison(s, data, 100, 120, 1200, 650); else SvgBars(s, results, 100, 120, 1200, 650, "MVS Score");
        s.Append("</svg>"); return s.ToString();
    }
    private static string BuildDashboardSvg(AnalysisData data, List<ResultRow> results)
    {
        var s = SvgStart(1800, 1200); s.Append("<rect width='100%' height='100%' fill='white'/><text x='60' y='55' font-size='32' font-family='Segoe UI' font-weight='bold'>MVS analysis dashboard</text>"); SvgBars(s, results, 70, 120, 760, 420, "MVS Score"); SvgScatter(s, results, 960, 120, 760, 420); SvgHistogram(s, data, 70, 690, 760, 390); SvgGroupComparison(s, data, 960, 690, 760, 390); s.Append("</svg>"); return s.ToString();
    }
    private static StringBuilder SvgStart(int w, int h) => new($"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}' viewBox='0 0 {w} {h}'>");
    private static void SvgBars(StringBuilder s, List<ResultRow> rows, int x, int y, int w, int h, string title)
    {
        s.Append($"<text x='{x}' y='{y-25}' font-size='24' font-family='Segoe UI' font-weight='bold'>{Escape(title)}</text><line x1='{x}' y1='{y+h}' x2='{x+w}' y2='{y+h}' stroke='#444'/>"); rows = rows.Where(r => double.IsFinite(r.Score)).ToList(); if (rows.Count == 0) return; int slot = w / rows.Count; double max = Math.Max(100, rows.Max(r => r.Score));
        for (int i=0;i<rows.Count;i++){int bh=(int)(h*rows[i].Score/max);int bx=x+i*slot+8;string c=rows[i].Candidate?"#107c10":"#0f6cbd";s.Append($"<rect x='{bx}' y='{y+h-bh}' width='{Math.Max(8,slot-16)}' height='{bh}' fill='{c}'/><text x='{bx}' y='{y+h+20}' font-size='11' font-family='Segoe UI' transform='rotate(35 {bx} {y+h+20})'>{Escape(rows[i].Metric)}</text>");}
    }
    private static void SvgScatter(StringBuilder s, List<ResultRow> rows, int x, int y, int w, int h)
    {
        s.Append($"<text x='{x}' y='{y-25}' font-size='24' font-family='Segoe UI' font-weight='bold'>Calibrated FPR vs power</text><line x1='{x}' y1='{y+h}' x2='{x+w}' y2='{y+h}' stroke='#444'/><line x1='{x}' y1='{y}' x2='{x}' y2='{y+h}' stroke='#444'/>");rows=rows.Where(r=>double.IsFinite(r.Fpr)&&double.IsFinite(r.Power)).ToList();if(rows.Count==0)return;double mf=Math.Max(.1,rows.Max(r=>r.Fpr)*1.15);foreach(var r in rows){int px=x+(int)(w*r.Fpr/mf),py=y+h-(int)(h*r.Power);s.Append($"<circle cx='{px}' cy='{py}' r='7' fill='{(r.Candidate?"#107c10":"#ca5010")}'/><text x='{px+10}' y='{py+4}' font-size='12' font-family='Segoe UI'>{Escape(r.Metric)}</text>");}
    }
    private static void SvgHistogram(StringBuilder s, AnalysisData data, int x, int y, int w, int h)
    {
        s.Append($"<text x='{x}' y='{y-25}' font-size='24' font-family='Segoe UI' font-weight='bold'>Measurement distribution</text>");double min=data.Observations.Min(o=>o.Value),max=data.Observations.Max(o=>o.Value);int bins=24;var count=new int[bins];foreach(var o in data.Observations){int b=Math.Clamp((int)((o.Value-min)/Math.Max(1,max-min)*bins),0,bins-1);count[b]++;}int mc=Math.Max(1,count.Max());for(int i=0;i<bins;i++){int bh=(int)(h*count[i]/(double)mc);s.Append($"<rect x='{x+i*w/bins}' y='{y+h-bh}' width='{Math.Max(1,w/bins-1)}' height='{bh}' fill='#0f6cbd' opacity='.75'/>");}string unit=UnitSuffix(data);s.Append($"<text x='{x}' y='{y+h+22}' font-size='12' font-family='Segoe UI'>{min:0.##}{Escape(unit)}</text><text x='{x+w-70}' y='{y+h+22}' font-size='12' font-family='Segoe UI'>{max:0.##}{Escape(unit)}</text>");
    }
    private static void SvgTrialTimeCourse(StringBuilder s, AnalysisData data, int x, int y, int w, int h)
    {
        s.Append($"<text x='{x}' y='{y-25}' font-size='24' font-family='Segoe UI' font-weight='bold'>Measurement across sequence</text>"); int maxTrial=Math.Max(1,data.Observations.Max(o=>o.Sequence));double min=data.Observations.Min(o=>o.Value),max=data.Observations.Max(o=>o.Value);
        for(int gi=0;gi<data.GroupNames.Length;gi++){var pts=new List<string>();for(int b=0;b<30;b++){int a=b*maxTrial/30+1,z=(b+1)*maxTrial/30;double[] values=data.Observations.Where(o=>o.Group==data.GroupNames[gi]&&o.Sequence>=a&&o.Sequence<=z).Select(o=>o.Value).ToArray();if(values.Length==0)continue;int px=x+(int)((b+.5)*w/30),py=y+h-(int)((values.Average()-min)/Math.Max(1,max-min)*h);pts.Add($"{px},{py}");}s.Append($"<polyline fill='none' stroke='{SvgPalette[gi%SvgPalette.Length]}' stroke-width='3' points='{string.Join(' ',pts)}'/>");}
    }
    private static void SvgGroupComparison(StringBuilder s, AnalysisData data, int x, int y, int w, int h)
    {
        double[] medians=data.GroupNames.Select(group=>Median(data.Entities.Where(p=>string.Equals(p.Group,group,StringComparison.OrdinalIgnoreCase)).Select(p=>p.Metrics[0]).ToArray())).ToArray();double max=Math.Max(1,medians.Max()*1.2);string[] colors=SvgPalette;int slot=w/medians.Length;
        s.Append($"<text x='{x}' y='{y-25}' font-size='24' font-family='Segoe UI' font-weight='bold'>Entity median value by group</text><line x1='{x}' y1='{y+h}' x2='{x+w}' y2='{y+h}' stroke='#444'/>");for(int i=0;i<medians.Length;i++){int bw=Math.Min(110,slot-12),bx=x+i*slot+(slot-bw)/2,bh=(int)(h*medians[i]/max);s.Append($"<rect x='{bx}' y='{y+h-bh}' width='{bw}' height='{bh}' fill='{colors[i%colors.Length]}'/><text x='{bx}' y='{y+h+22}' font-size='12' font-family='Segoe UI'>{Escape(data.GroupNames[i])}</text><text x='{bx}' y='{y+h-bh-8}' font-size='12' font-family='Segoe UI'>{medians[i]:0.##}</text>");}
    }
    private static void SvgDataQuality(StringBuilder s, AnalysisData data, int x, int y, int w, int h)
    {
        s.Append($"<text x='{x}' y='{y-25}' font-size='24' font-family='Segoe UI' font-weight='bold'>Valid measurements by entity</text>");var people=data.Entities.OrderBy(p=>p.Measurements).ToArray();int max=Math.Max(1,people.Max(p=>p.Measurements));double bw=w/(double)Math.Max(1,people.Length);for(int i=0;i<people.Length;i++){int bh=(int)(h*people[i].Measurements/(double)max);string color=SvgPalette[GroupIndex(data,people[i].Group)%SvgPalette.Length];s.Append($"<rect x='{x+i*bw:0.##}' y='{y+h-bh}' width='{Math.Max(1,bw-1):0.##}' height='{bh}' fill='{color}'/>");}
    }
    private static string Escape(string value) => value.Replace("&", "&amp;").Replace("<", "&lt;").Replace(">", "&gt;").Replace("'", "&apos;");

    internal sealed record FigureSpec(string Id, string Title, string Chart, string Source, string X, string Y, string Group);
    private sealed record SpecPoint(string Label, double X, double Value, int GroupIndex);

    private static string MapToBuiltIn(FigureSpec spec) => spec.Chart switch
    {
        "histogram" => "value_distribution",
        "scatter" => "fpr_power",
        "line" or "box" => "group_comparison",
        _ => spec.Source is "trials" or "observations" ? "value_distribution" : spec.Source is "participants" or "entities" ? "group_comparison" : "mvs_score"
    };

    // A template is found by file name OR by its declared id, so renaming a file
    // no longer makes a plugin template unreachable.
    private static FigureSpec? LoadSpec(string id)
    {
        var files = new List<string>();
        string customFolder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MVS_Analyzer", "figure-templates");
        if (Directory.Exists(customFolder)) files.AddRange(Directory.GetFiles(customFolder, "*.json"));
        try { files.AddRange(PluginManager.EnabledTemplateFiles()); } catch { }
        foreach (string file in files.Where(x => string.Equals(Path.GetFileNameWithoutExtension(x), id, StringComparison.OrdinalIgnoreCase)).Concat(files))
        {
            FigureSpec? spec = ParseSpec(file); if (spec == null) continue;
            if (string.Equals(Path.GetFileNameWithoutExtension(file), id, StringComparison.OrdinalIgnoreCase) || string.Equals(spec.Id, id, StringComparison.OrdinalIgnoreCase)) return spec;
        }
        return null;
    }

    private static FigureSpec? ParseSpec(string file)
    {
        try
        {
            using JsonDocument doc = JsonDocument.Parse(File.ReadAllText(file)); JsonElement root = doc.RootElement;
            string id = Str(root, "id", Path.GetFileNameWithoutExtension(file));
            return new FigureSpec(id, Str(root, "title", Str(root, "name", id)), Str(root, "chart", "bar").ToLowerInvariant(), Str(root, "source", "results").ToLowerInvariant(), Str(root, "x", "metric").ToLowerInvariant(), Str(root, "y", "mvs_score").ToLowerInvariant(), Str(root, "grouping", Str(root, "group", "none")).ToLowerInvariant());
        }
        catch { return null; }
    }

    private static string Str(JsonElement root, string name, string fallback)
    {
        if (!root.TryGetProperty(name, out JsonElement value) || value.ValueKind != JsonValueKind.String) return fallback;
        string? text = value.GetString(); return string.IsNullOrWhiteSpace(text) ? fallback : text.Trim();
    }

    private static void DrawMissing(Graphics g, Rectangle p, string id)
    {
        using var head = new Font("Segoe UI", 16, FontStyle.Bold); using var body = new Font("Segoe UI", 10);
        g.DrawString("Template not found", head, Brushes.Firebrick, p.Left, p.Top);
        g.DrawString($"'{id}' is neither a built-in template nor a readable plugin or custom template. Nothing was drawn instead of substituting another chart.", body, Brushes.Black, new RectangleF(p.Left, p.Top + 34, Math.Max(200, p.Width - 20), 90));
    }

    private static void DrawSpec(Graphics g, Rectangle p, FigureSpec spec, AnalysisData data, List<ResultRow> results)
    {
        List<SpecPoint> series = BuildSeries(spec, data, results);
        if (series.Count == 0)
        {
            Title(g, p, spec.Title); Axes(g, p);
            using var body = new Font("Segoe UI", 11);
            g.DrawString("No finite values for this template.", body, Brushes.Black, p.Left + 12, p.Top + 12); return;
        }
        switch (spec.Chart)
        {
            case "scatter": DrawSpecScatter(g, p, spec, series); break;
            case "histogram": DrawSpecHistogram(g, p, spec, series, data); break;
            case "line": DrawSpecLine(g, p, spec, series, data); break;
            case "box": DrawSpecBox(g, p, spec, series, data); break;
            default: DrawSpecBars(g, p, spec, series, data); break;
        }
    }

    private static List<SpecPoint> BuildSeries(FigureSpec spec, AnalysisData data, List<ResultRow> results)
    {
        var points = new List<SpecPoint>();
        switch (spec.Source)
        {
            case "trials":
            case "observations":
                foreach (Observation o in data.Observations) points.Add(new SpecPoint(o.Entity, o.Sequence, o.Value, GroupIndex(data, o.Group)));
                break;
            case "participants":
            case "entities":
                foreach (EntityResult e in data.Entities) points.Add(new SpecPoint(e.Entity, e.Measurements, EntityValue(spec.Y, e), GroupIndex(data, e.Group)));
                break;
            default:
                for (int i = 0; i < results.Count; i++) points.Add(new SpecPoint(results[i].Metric, SpecX(spec.X, results[i], i), MetricValue(spec.Y, results[i]), i));
                break;
        }
        return points.Where(x => double.IsFinite(x.Value) && double.IsFinite(x.X)).ToList();
    }

    private static double SpecX(string x, ResultRow r, int index) => x switch { "fpr" => r.Fpr, "power" => r.Power, "mvs_score" or "score" => r.Score, _ => index };
    private static double MetricValue(string y, ResultRow r) => y switch
    {
        "power" => r.Power, "fpr" => r.Fpr, "robustness" => r.Robustness, "repeatability" => r.Repeatability,
        "coverage" => r.Coverage, "p" or "p_value" or "global_p" => r.PValue, "median" or "median_rt" => r.FirstGroupMedian, _ => r.Score
    };
    private static double EntityValue(string y, EntityResult e) => y switch
    {
        "measurements" => e.Measurements,
        "sd" or "standard_deviation" or "spread" => e.Metrics.Length > 1 ? e.Metrics[1] : double.NaN,
        _ => e.Metrics.Length > 0 ? e.Metrics[0] : double.NaN
    };
    private static double MedianSafe(IEnumerable<double> values)
    {
        double[] sorted = values.Where(double.IsFinite).ToArray(); if (sorted.Length == 0) return double.NaN;
        Array.Sort(sorted); return sorted.Length % 2 == 1 ? sorted[sorted.Length / 2] : (sorted[sorted.Length / 2 - 1] + sorted[sorted.Length / 2]) / 2;
    }
    private static double Quantile(double[] sorted, double q)
    {
        if (sorted.Length == 0) return double.NaN; if (sorted.Length == 1) return sorted[0];
        double position = q * (sorted.Length - 1); int low = (int)Math.Floor(position); int high = Math.Min(sorted.Length - 1, low + 1);
        return sorted[low] + (sorted[high] - sorted[low]) * (position - low);
    }
    private static string Fmt(double value) => Math.Abs(value) >= 1000 ? value.ToString("0", CultureInfo.InvariantCulture) : value.ToString("0.##", CultureInfo.InvariantCulture);
    private static void ValueAxis(Graphics g, Rectangle p, Font font, double min, double max)
    {
        using var gridPen = new Pen(Grid);
        for (int i = 0; i <= 4; i++) { int y = p.Bottom - i * p.Height / 4; g.DrawLine(gridPen, p.Left, y, p.Right, y); g.DrawString(Fmt(min + (max - min) * i / 4), font, Brushes.Black, p.Left - 56, y - 7); }
    }

    private static void DrawSpecBars(Graphics g, Rectangle p, FigureSpec spec, List<SpecPoint> points, AnalysisData data)
    {
        Title(g, p, spec.Title); Axes(g, p); using var font = new Font("Segoe UI", 9);
        bool byGroup = spec.Group == "group" && data.GroupNames.Length > 0 && spec.Source is not ("results" or "calibration");
        var bars = new List<(string Label, double Value, int Color)>();
        if (byGroup)
            for (int i = 0; i < data.GroupNames.Length; i++) { double value = MedianSafe(points.Where(x => x.GroupIndex == i).Select(x => x.Value)); if (double.IsFinite(value)) bars.Add((data.GroupNames[i], value, i)); }
        else for (int i = 0; i < points.Count; i++) bars.Add((points[i].Label, points[i].Value, i));
        if (bars.Count == 0) return;
        double max = Math.Max(bars.Max(x => x.Value) * 1.15, 1e-9); double min = Math.Min(0, bars.Min(x => x.Value));
        ValueAxis(g, p, font, min, max);
        int slot = Math.Max(6, p.Width / bars.Count); bool labels = bars.Count <= 24;
        for (int i = 0; i < bars.Count; i++)
        {
            int h = (int)(p.Height * (bars[i].Value - min) / (max - min)); int x = p.Left + i * slot + 3; int w = Math.Max(3, slot - 8);
            using var brush = new SolidBrush(GroupColor(bars[i].Color)); g.FillRectangle(brush, x, p.Bottom - h, w, h);
            if (!labels) continue;
            g.DrawString(Fmt(bars[i].Value), font, Brushes.Black, x, p.Bottom - h - 18);
            g.TranslateTransform(x + w / 2f, p.Bottom + 8); g.RotateTransform(40); g.DrawString(bars[i].Label, font, Brushes.Black, 0, 0); g.ResetTransform();
        }
        if (!labels) g.DrawString($"{bars.Count} items", font, Brushes.Black, p.Left, p.Bottom + 12);
    }

    private static void DrawSpecScatter(Graphics g, Rectangle p, FigureSpec spec, List<SpecPoint> points)
    {
        Title(g, p, spec.Title); Axes(g, p); using var font = new Font("Segoe UI", 9); using var gridPen = new Pen(Grid);
        double minX = points.Min(x => x.X), maxX = points.Max(x => x.X); if (maxX - minX < 1e-12) maxX = minX + 1;
        double minY = Math.Min(0, points.Min(x => x.Value)), maxY = points.Max(x => x.Value); if (maxY - minY < 1e-12) maxY = minY + 1;
        ValueAxis(g, p, font, minY, maxY);
        for (int i = 0; i <= 5; i++)
        {
            int x = p.Left + i * p.Width / 5; g.DrawLine(gridPen, x, p.Top, x, p.Bottom);
            string text = Fmt(minX + (maxX - minX) * i / 5); SizeF size = g.MeasureString(text, font);
            g.DrawString(text, font, Brushes.Black, x - size.Width / 2, p.Bottom + 8);
        }
        bool labels = points.Count <= 20;
        foreach (SpecPoint point in points)
        {
            int x = p.Left + (int)(p.Width * (point.X - minX) / (maxX - minX)); int y = p.Bottom - (int)(p.Height * (point.Value - minY) / (maxY - minY));
            using var brush = new SolidBrush(GroupColor(point.GroupIndex)); g.FillEllipse(brush, x - 6, y - 6, 12, 12);
            if (labels) g.DrawString(point.Label, font, Brushes.Black, x + 9, y - 8);
        }
        g.DrawString(spec.X, font, Brushes.Black, p.Right - 60, p.Bottom + 30); g.DrawString(spec.Y, font, Brushes.Black, p.Left - 56, p.Top - 22);
    }

    private static void DrawSpecHistogram(Graphics g, Rectangle p, FigureSpec spec, List<SpecPoint> points, AnalysisData data)
    {
        Title(g, p, spec.Title); Axes(g, p); using var font = new Font("Segoe UI", 9);
        double min = points.Min(x => x.Value), max = points.Max(x => x.Value); if (max - min < 1e-12) max = min + 1;
        int bins = 24; bool byGroup = spec.Group == "group" && data.GroupNames.Length > 0;
        int seriesCount = byGroup ? data.GroupNames.Length : 1;
        var counts = new int[seriesCount][]; for (int k = 0; k < seriesCount; k++) counts[k] = new int[bins];
        foreach (SpecPoint point in points)
        {
            int b = Math.Clamp((int)((point.Value - min) / (max - min) * bins), 0, bins - 1);
            counts[byGroup ? Math.Clamp(point.GroupIndex, 0, seriesCount - 1) : 0][b]++;
        }
        int peak = Math.Max(1, counts.SelectMany(x => x).Max()); float bw = p.Width / (float)bins;
        ValueAxis(g, p, font, 0, peak);
        for (int b = 0; b < bins; b++)
            for (int k = 0; k < seriesCount; k++)
            {
                float h = p.Height * counts[k][b] / (float)peak; if (h <= 0) continue;
                using var brush = new SolidBrush(seriesCount == 1 ? Blue : Color.FromArgb(140, GroupColor(k)));
                g.FillRectangle(brush, p.Left + b * bw, p.Bottom - h, Math.Max(1, bw - 1), h);
            }
        g.DrawString(Fmt(min), font, Brushes.Black, p.Left, p.Bottom + 8); g.DrawString(Fmt(max), font, Brushes.Black, p.Right - 50, p.Bottom + 8);
        if (byGroup) for (int k = 0; k < seriesCount; k++) { using var legend = new SolidBrush(GroupColor(k)); g.FillRectangle(legend, p.Right - 130, p.Top + 4 + k * 18, 12, 12); g.DrawString(data.GroupNames[k], font, Brushes.Black, p.Right - 114, p.Top + 2 + k * 18); }
        g.DrawString(spec.Y, font, Brushes.Black, p.Right - 160, p.Bottom + 30); g.DrawString("count", font, Brushes.Black, p.Left - 56, p.Top - 22);
    }

    private static void DrawSpecLine(Graphics g, Rectangle p, FigureSpec spec, List<SpecPoint> points, AnalysisData data)
    {
        Title(g, p, spec.Title); Axes(g, p); using var font = new Font("Segoe UI", 9);
        double minX = points.Min(x => x.X), maxX = points.Max(x => x.X); if (maxX - minX < 1e-12) maxX = minX + 1;
        double minY = points.Min(x => x.Value), maxY = points.Max(x => x.Value); if (maxY - minY < 1e-12) maxY = minY + 1;
        ValueAxis(g, p, font, minY, maxY);
        bool byGroup = spec.Group == "group" && data.GroupNames.Length > 0; int seriesCount = byGroup ? data.GroupNames.Length : 1; int bins = 30;
        for (int k = 0; k < seriesCount; k++)
        {
            var line = new List<PointF>();
            for (int b = 0; b < bins; b++)
            {
                double from = minX + (maxX - minX) * b / bins, to = minX + (maxX - minX) * (b + 1) / bins;
                double[] values = points.Where(x => (!byGroup || x.GroupIndex == k) && x.X >= from && (x.X < to || (b == bins - 1 && x.X <= to))).Select(x => x.Value).ToArray();
                if (values.Length == 0) continue;
                float px = p.Left + (b + .5f) * p.Width / bins; float py = p.Bottom - (float)((values.Average() - minY) / (maxY - minY) * p.Height);
                line.Add(new PointF(px, py));
            }
            if (line.Count == 0) continue;
            using var pen = new Pen(GroupColor(k), 3); if (line.Count > 1) g.DrawLines(pen, line.ToArray());
            using var brush = new SolidBrush(GroupColor(k)); foreach (PointF point in line) g.FillEllipse(brush, point.X - 3, point.Y - 3, 6, 6);
            if (byGroup) g.DrawString(data.GroupNames[k], font, brush, p.Right - 100, p.Top + k * 20);
        }
        g.DrawString(Fmt(minX), font, Brushes.Black, p.Left, p.Bottom + 8); g.DrawString(Fmt(maxX), font, Brushes.Black, p.Right - 50, p.Bottom + 8);
        g.DrawString(spec.X, font, Brushes.Black, p.Right - 60, p.Bottom + 30); g.DrawString(spec.Y, font, Brushes.Black, p.Left - 56, p.Top - 22);
    }

    private static void DrawSpecBox(Graphics g, Rectangle p, FigureSpec spec, List<SpecPoint> points, AnalysisData data)
    {
        Title(g, p, spec.Title); Axes(g, p); using var font = new Font("Segoe UI", 9);
        int seriesCount = data.GroupNames.Length > 0 ? data.GroupNames.Length : 1;
        var boxes = new List<(string Label, double[] Sorted, int Color)>();
        for (int k = 0; k < seriesCount; k++)
        {
            double[] values = points.Where(x => data.GroupNames.Length == 0 || x.GroupIndex == k).Select(x => x.Value).Where(double.IsFinite).ToArray();
            if (values.Length == 0) continue; Array.Sort(values);
            boxes.Add((data.GroupNames.Length > k ? data.GroupNames[k] : "all", values, k));
        }
        if (boxes.Count == 0) return;
        double min = boxes.Min(x => x.Sorted[0]), max = boxes.Max(x => x.Sorted[^1]); if (max - min < 1e-12) max = min + 1;
        ValueAxis(g, p, font, min, max);
        int slot = p.Width / boxes.Count;
        for (int i = 0; i < boxes.Count; i++)
        {
            double[] sorted = boxes[i].Sorted;
            float Y(double value) => p.Bottom - (float)((value - min) / (max - min) * p.Height);
            float q1 = Y(Quantile(sorted, .25)), q2 = Y(Quantile(sorted, .5)), q3 = Y(Quantile(sorted, .75)), lo = Y(sorted[0]), hi = Y(sorted[^1]);
            int width = Math.Min(120, slot - 24); int x = p.Left + i * slot + (slot - width) / 2;
            using var pen = new Pen(GroupColor(boxes[i].Color), 2); using var fill = new SolidBrush(Color.FromArgb(60, GroupColor(boxes[i].Color)));
            g.DrawLine(pen, x + width / 2, hi, x + width / 2, lo);
            g.FillRectangle(fill, x, q3, width, Math.Max(1, q1 - q3)); g.DrawRectangle(pen, x, q3, width, Math.Max(1, q1 - q3));
            g.DrawLine(pen, x, q2, x + width, q2);
            g.DrawString(boxes[i].Label, font, Brushes.Black, x, p.Bottom + 12);
            g.DrawString(Fmt(Quantile(sorted, .5)), font, Brushes.Black, x, q2 - 18);
        }
        g.DrawString(spec.Y, font, Brushes.Black, p.Left - 56, p.Top - 22);
    }
}
