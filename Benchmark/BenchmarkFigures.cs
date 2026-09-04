using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Globalization;

namespace MvsAnalyzer.Benchmarking;

internal sealed record FigureSize(string Suffix, int Width, int Height, int TopSafe, int BottomSafe);

/// <summary>
/// Draws the benchmark figures with System.Drawing only, which the program already uses. No
/// charting package is added, because a plotting dependency would have to be version-matched
/// forever and this program deliberately has none.
///
/// The palette is Okabe-Ito: it stays readable for the eight percent of men with red-green colour
/// blindness, and it survives the compression that social platforms apply. Every figure carries the
/// seed and the protocol hash in its footer, so a screenshot can still be traced back to the run
/// that produced it.
/// </summary>
internal static class BenchmarkFigures
{
    public static readonly FigureSize Print = new("print", 2000, 1250, 0, 0);
    public static readonly FigureSize Story = new("story", 1080, 1920, 250, 340);
    public static readonly FigureSize Square = new("square", 1080, 1350, 40, 70);
    public static readonly FigureSize Landscape = new("wide", 1200, 675, 16, 24);

    private static readonly Color Ink = Color.FromArgb(22, 24, 30);
    private static readonly Color Muted = Color.FromArgb(112, 118, 130);
    private static readonly Color Faint = Color.FromArgb(226, 229, 234);
    private static readonly Color Paper = Color.White;

    private static readonly Color Vermillion = Color.FromArgb(213, 94, 0);
    private static readonly Color Orange = Color.FromArgb(230, 159, 0);
    private static readonly Color Blue = Color.FromArgb(0, 114, 178);
    private static readonly Color Sky = Color.FromArgb(86, 180, 233);
    private static readonly Color Purple = Color.FromArgb(204, 121, 167);
    private static readonly Color Green = Color.FromArgb(0, 158, 115);
    private static readonly Color Slate = Color.FromArgb(130, 136, 148);

    private static readonly Color[] ProcedureColors = { Vermillion, Orange, Blue, Sky, Purple, Green, Slate };

    private static string L(bool russian, string english, string russianText) => russian ? russianText : english;

    public static List<string> Generate(BenchmarkOutcome outcome, string folder, bool russian)
    {
        Directory.CreateDirectory(folder);
        var files = new List<string>();
        string stamp = L(russian, "seed ", "seed ") + outcome.Seed.ToString(CultureInfo.InvariantCulture) +
            "  ·  " + BenchmarkProtocol.Version +
            "  ·  " + L(russian, "protocol ", "протокол ") + Short(BenchmarkProtocol.Hash) +
            "  ·  " + L(russian, "formula ", "формула ") + Short(OutputExporter.FormulaHash);
        string brand = "MVS Analyzer  ·  " + outcome.RunId;

        foreach (FigureSize size in new[] { Print, Story, Square, Landscape })
            Add(files, folder, "fig1_error_control", size, board => ErrorControl(board, outcome, russian, stamp, brand));

        foreach (FigureSize size in new[] { Print, Story, Square, Landscape })
            Add(files, folder, "fig2_power_vs_error", size, board => PowerVersusError(board, outcome, russian, stamp, brand));

        Add(files, folder, "fig3_power_curves", Print, board => PowerCurves(board, outcome, russian, stamp, brand));
        Add(files, folder, "fig4_metric_stability", Print, board => Stability(board, outcome, russian, stamp, brand));
        Add(files, folder, "fig5_contamination", Print, board => Contamination(board, outcome, russian, stamp, brand));
        Add(files, folder, "fig6_metric_heatmap", Print, board => MetricHeatmap(board, outcome, russian, stamp, brand));
        Add(files, folder, "fig7_verdicts", Print, board => Verdicts(board, outcome, russian, stamp, brand));
        Add(files, folder, "fig7_verdicts", Square, board => Verdicts(board, outcome, russian, stamp, brand));

        return files;
    }

    private static void Add(List<string> files, string folder, string name, FigureSize size, Action<Board> draw)
    {
        string path = Path.Combine(folder, name + "_" + size.Suffix + ".png");
        using var board = new Board(size);
        draw(board);
        board.Bitmap.Save(path, ImageFormat.Png);
        files.Add(path);
    }

    private static string Short(string hash) => hash.Length >= 12 ? hash.Substring(0, 12) : hash;

    // ---------------- figure 1: the headline ----------------

    private static void ErrorControl(Board board, BenchmarkOutcome outcome, bool russian, string stamp, string brand)
    {
        ConditionSummary? primary = outcome.Find("primary_null");
        double cherry = primary != null ? primary.Rate(BenchmarkProcedures.CherryPick) : double.NaN;
        double gated = primary != null ? primary.Rate(BenchmarkProcedures.MvsStrict) : double.NaN;
        int replications = primary != null ? primary.Completed : 0;

        float top = Header(board,
            L(russian, "There is no difference in this data at all", "В этих данных разницы нет вообще"),
            L(russian,
                "Two groups drawn from one population. How often does each way of choosing a metric announce a discovery that is not there? The honest answer is five percent.",
                "Две группы из одной генеральной совокупности. Как часто каждый способ выбора метрики объявляет открытие, которого нет? Честный ответ — пять процентов."));

        float bottom = board.Height - board.BottomSafe - 70 * board.S;
        float side = 34 * board.S;

        if (double.IsFinite(cherry) && double.IsFinite(gated))
        {
            using var bigFont = board.Typeface(44, FontStyle.Bold);
            using var capFont = board.Typeface(11.5f);
            using var alarmBrush = new SolidBrush(Vermillion);
            using var goodBrush = new SolidBrush(Green);
            using var mutedBrush = new SolidBrush(Muted);
            string left = BenchmarkRunner.Pct(cherry);
            string right = BenchmarkRunner.Pct(gated);
            SizeF leftSize = board.G.MeasureString(left, bigFont);
            SizeF rightSize = board.G.MeasureString(right, bigFont);
            board.G.DrawString(left, bigFont, alarmBrush, side, top);
            board.G.DrawString(L(russian, "picking the best of ten metrics", "выбор лучшей из десяти метрик"),
                capFont, mutedBrush, side, top + leftSize.Height - 4 * board.S);
            float secondX = side + Math.Max(leftSize.Width + 60 * board.S, board.Width * .42f);
            if (secondX + rightSize.Width + side > board.Width) secondX = side;
            float secondY = secondX == side ? top + leftSize.Height + 40 * board.S : top;
            board.G.DrawString(right, bigFont, goodBrush, secondX, secondY);
            board.G.DrawString(L(russian, "same data, MVS gate respected", "те же данные, порог MVS соблюдён"),
                capFont, mutedBrush, secondX, secondY + rightSize.Height - 4 * board.S);
            top = secondY + rightSize.Height + 46 * board.S;
        }

        var labels = new string[BenchmarkProcedures.Count];
        var values = new double[BenchmarkProcedures.Count];
        for (int i = 0; i < BenchmarkProcedures.Count; i++)
        {
            labels[i] = BenchmarkProcedures.Label(i, russian);
            values[i] = primary != null ? primary.Rate(i) : double.NaN;
        }

        double max = BenchmarkProtocol.Alpha * 1.4;
        foreach (double value in values) if (double.IsFinite(value) && value > max) max = value;
        max = NiceCeiling(max);

        var plot = new RectangleF(side, top, board.Width - 2 * side, Math.Max(120 * board.S, bottom - top));
        HorizontalBars(board, plot, labels, values, ProcedureColors, max,
            BenchmarkProtocol.Alpha, L(russian, "promised 5%", "обещанные 5%"));

        Footer(board,
            L(russian, "false discoveries out of ", "ложные открытия из ") +
                replications.ToString(CultureInfo.InvariantCulture) +
                L(russian, " simulated studies with no real effect  ·  ", " симулированных исследований без реального эффекта  ·  ") + stamp,
            brand);
    }

    // ---------------- figure 2: what the control costs ----------------

    private static void PowerVersusError(Board board, BenchmarkOutcome outcome, bool russian, string stamp, string brand)
    {
        ConditionSummary? nullCondition = outcome.Find("primary_null");
        ConditionSummary? effectCondition = outcome.Find("power_location_105");

        float top = Header(board,
            L(russian, "Being right is not enough. You have to be right without cheating",
                "Мало быть правым. Надо быть правым без подтасовки"),
            L(russian,
                "Horizontal: how often each rule cries wolf when nothing is there. Vertical: how often it finds a real five percent shift. Bottom right is what everybody wants and nobody can have.",
                "По горизонтали: как часто правило кричит о находке на пустом месте. По вертикали: как часто оно находит реальный сдвиг в пять процентов."));

        float side = 34 * board.S;
        float bottom = board.Height - board.BottomSafe - 70 * board.S;
        var names = new List<string>();
        var xs = new List<double>();
        var ys = new List<double>();
        var colors = new List<Color>();
        for (int i = 0; i < BenchmarkProcedures.Count; i++)
        {
            double x = nullCondition != null ? nullCondition.Rate(i) : double.NaN;
            double y = effectCondition != null ? effectCondition.Rate(i) : double.NaN;
            if (!double.IsFinite(x) || !double.IsFinite(y)) continue;
            names.Add(BenchmarkProcedures.ShortLabel(i, russian));
            xs.Add(x);
            ys.Add(y);
            colors.Add(ProcedureColors[i]);
        }
        if (effectCondition != null)
        {
            int oracle = effectCondition.OracleMetric();
            if (oracle >= 0 && nullCondition != null)
            {
                names.Add(L(russian, "oracle: ", "оракул: ") + AnalysisEngine.MetricKeys[oracle]);
                xs.Add(nullCondition.MetricRate(oracle));
                ys.Add(effectCondition.MetricRate(oracle));
                colors.Add(Ink);
            }
        }

        double xMax = NiceCeiling(Math.Max(BenchmarkProtocol.Alpha * 1.6, xs.Count == 0 ? 0 : xs.Max()));
        var plot = new RectangleF(side, top, board.Width - 2 * side, Math.Max(140 * board.S, bottom - top));
        Scatter(board, plot, names.ToArray(), xs.ToArray(), ys.ToArray(), colors.ToArray(), xMax, 1.0,
            L(russian, "false discoveries when nothing is there", "ложные открытия на пустом месте"),
            L(russian, "real effects found", "найденные реальные эффекты"),
            BenchmarkProtocol.Alpha, L(russian, "promised 5%", "обещанные 5%"));

        Footer(board, L(russian, "effect: every entity in one group shifted by 5%  ·  ",
            "эффект: все объекты одной группы сдвинуты на 5%  ·  ") + stamp, brand);
    }

    // ---------------- figure 3: power curves ----------------

    private static void PowerCurves(Board board, BenchmarkOutcome outcome, bool russian, string stamp, string brand)
    {
        float top = Header(board,
            L(russian, "How big does an effect have to be before each rule notices it",
                "Насколько большим должен быть эффект, чтобы правило его заметило"),
            L(russian,
                "Left: the level of one group is multiplied. Right: only its spread is multiplied, the level is untouched. A single metric fixed in advance cannot win both panels; that is the whole reason this program exists.",
                "Слева: уровень одной группы умножается. Справа: умножается только разброс, уровень не тронут. Одна заранее выбранная метрика не может выиграть на обоих панелях."));

        float side = 34 * board.S;
        float bottom = board.Height - board.BottomSafe - 108 * board.S;
        float gap = 44 * board.S;
        float panelWidth = (board.Width - 2 * side - gap) / 2;
        var names = new string[BenchmarkProcedures.Count];
        for (int i = 0; i < BenchmarkProcedures.Count; i++) names[i] = BenchmarkProcedures.ShortLabel(i, russian);

        DrawCurvePanel(board, new RectangleF(side, top, panelWidth, bottom - top), outcome,
            "power_location_", BenchmarkProtocol.LocationGrid, russian,
            L(russian, "level shifted by a factor of", "уровень умножен на"),
            L(russian, "real effects found", "найденные эффекты"));

        DrawCurvePanel(board, new RectangleF(side + panelWidth + gap, top, panelWidth, bottom - top), outcome,
            "power_dispersion_", BenchmarkProtocol.DispersionGrid, russian,
            L(russian, "spread multiplied by a factor of", "разброс умножен на"),
            "");

        Legend(board, new RectangleF(side, bottom + 18 * board.S, board.Width - 2 * side, 70 * board.S), names, ProcedureColors);
        Footer(board, stamp, brand);
    }

    private static void DrawCurvePanel(Board board, RectangleF plot, BenchmarkOutcome outcome, string prefix, double[] grid, bool russian, string xTitle, string yTitle)
    {
        var series = new double[BenchmarkProcedures.Count][];
        for (int procedure = 0; procedure < BenchmarkProcedures.Count; procedure++)
        {
            series[procedure] = new double[grid.Length];
            for (int point = 0; point < grid.Length; point++)
            {
                ConditionSummary? condition = outcome.Find(prefix + ((int)Math.Round(grid[point] * 100)).ToString(CultureInfo.InvariantCulture));
                series[procedure][point] = condition != null ? condition.Rate(procedure) : double.NaN;
            }
        }
        Lines(board, plot, grid, series, ProcedureColors, 1.0, xTitle, yTitle,
            BenchmarkProtocol.Alpha, russian ? "5%" : "5%", "0.00");
    }

    // ---------------- figure 4: stability ----------------

    private static void Stability(Board board, BenchmarkOutcome outcome, bool russian, string stamp, string brand)
    {
        float top = Header(board,
            L(russian, "Show it half the data and it picks the same metric",
                "Покажи ему половину данных — он выберет ту же метрику"),
            L(russian,
                "Each study is split into two independent halves and ranked twice. A rule that reshuffles its answer every time it sees new subjects is measuring noise, not value.",
                "Каждое исследование делится на две независимые половины и ранжируется дважды. Правило, которое каждый раз меняет ответ, измеряет шум, а не ценность."));

        float side = 34 * board.S;
        float bottom = board.Height - board.BottomSafe - 70 * board.S;
        float gap = 44 * board.S;
        float leftWidth = (board.Width - 2 * side - gap) * .54f;

        Histogram(board, new RectangleF(side, top, leftWidth, bottom - top), outcome.Stability.Tau, 16, -1, 1, Blue,
            L(russian, "agreement between halves (Kendall tau)", "согласие половин (тау Кендалла)"),
            L(russian, "splits", "разбиений"));

        var labels = new List<string>();
        var values = new List<double>();
        var colors = new List<Color>();
        int total = 0;
        foreach (int count in outcome.Stability.TopMetricCounts) total += count;
        for (int metric = 0; metric < outcome.Stability.TopMetricCounts.Length; metric++)
        {
            if (outcome.Stability.TopMetricCounts[metric] == 0) continue;
            labels.Add(AnalysisEngine.MetricKeys[metric].Replace('_', ' '));
            values.Add(total == 0 ? 0 : outcome.Stability.TopMetricCounts[metric] / (double)total);
            colors.Add(Blue);
        }
        if (labels.Count == 0)
        {
            labels.Add(L(russian, "no usable split", "нет годных разбиений"));
            values.Add(0);
            colors.Add(Slate);
        }

        var rightPlot = new RectangleF(side + leftWidth + gap, top, board.Width - 2 * side - leftWidth - gap, bottom - top);
        using (var font = board.Typeface(12, FontStyle.Bold))
        using (var brush = new SolidBrush(Ink))
            board.G.DrawString(L(russian, "Which metric came first", "Какая метрика оказалась первой"),
                font, brush, rightPlot.X, rightPlot.Y);
        var barsPlot = new RectangleF(rightPlot.X, rightPlot.Y + 34 * board.S, rightPlot.Width, rightPlot.Height - 34 * board.S);
        HorizontalBars(board, barsPlot, labels.ToArray(), values.ToArray(), colors.ToArray(), 1.0, null, "");

        Footer(board,
            L(russian, "median tau ", "медианная тау ") + BenchmarkRunner.Num(outcome.Stability.MedianTau) +
            L(russian, ", same winner in ", ", тот же лидер в ") + BenchmarkRunner.Pct(outcome.Stability.TopOneAgreement) +
            L(russian, " of splits  ·  ", " разбиений  ·  ") + stamp, brand);
    }

    // ---------------- figure 5: contamination ----------------

    private static void Contamination(Board board, BenchmarkOutcome outcome, bool russian, string stamp, string brand)
    {
        float top = Header(board,
            L(russian, "Real recordings are dirty. Does the guarantee survive it",
                "Реальные записи грязные. Выживает ли гарантия"),
            L(russian,
                "Still no real difference between the groups, but a growing share of measurements is replaced by an artefact five standard deviations away, the way a missed step or a dropped frame looks in practice.",
                "Разницы между группами по-прежнему нет, но всё большая доля измерений заменяется артефактом в пять стандартных отклонений — так выглядит сбой шага или потерянный кадр."));

        float side = 34 * board.S;
        float bottom = board.Height - board.BottomSafe - 108 * board.S;
        var grid = new double[BenchmarkProtocol.ContaminationGrid.Length + 1];
        grid[0] = 0;
        for (int i = 0; i < BenchmarkProtocol.ContaminationGrid.Length; i++) grid[i + 1] = BenchmarkProtocol.ContaminationGrid[i];

        var series = new double[BenchmarkProcedures.Count][];
        for (int procedure = 0; procedure < BenchmarkProcedures.Count; procedure++)
        {
            series[procedure] = new double[grid.Length];
            for (int point = 0; point < grid.Length; point++)
            {
                ConditionSummary? condition = point == 0
                    ? outcome.Find("primary_null")
                    : outcome.Find("robust_null_" + ((int)Math.Round(grid[point] * 100)).ToString(CultureInfo.InvariantCulture));
                series[procedure][point] = condition != null ? condition.Rate(procedure) : double.NaN;
            }
        }

        double max = BenchmarkProtocol.Alpha * 1.4;
        foreach (double[] line in series) foreach (double value in line) if (double.IsFinite(value) && value > max) max = value;

        var names = new string[BenchmarkProcedures.Count];
        for (int i = 0; i < BenchmarkProcedures.Count; i++) names[i] = BenchmarkProcedures.ShortLabel(i, russian);

        var plot = new RectangleF(side, top, board.Width - 2 * side, bottom - top);
        Lines(board, plot, grid, series, ProcedureColors, NiceCeiling(max),
            L(russian, "share of corrupted measurements", "доля испорченных измерений"),
            L(russian, "false discoveries", "ложные открытия"),
            BenchmarkProtocol.Alpha, "5%", "0%");
        Legend(board, new RectangleF(side, bottom + 18 * board.S, board.Width - 2 * side, 70 * board.S), names, ProcedureColors);
        Footer(board, stamp, brand);
    }

    // ---------------- figure 6: no single metric wins ----------------

    private static void MetricHeatmap(Board board, BenchmarkOutcome outcome, bool russian, string stamp, string brand)
    {
        float top = Header(board,
            L(russian, "No single metric is best everywhere", "Ни одна метрика не лучшая всюду"),
            L(russian,
                "Each cell is how often that one metric alone declares a difference. In the first column there is nothing to find, so low is correct. Everywhere else high is correct. Read across a row: every metric has a column where it loses.",
                "Каждая клетка — как часто одна эта метрика объявляет различие. В первом столбце находить нечего, там правильно мало. В остальных правильно много."));

        var columns = new List<ConditionSummary>();
        var columnLabels = new List<string>();
        ConditionSummary? nullCondition = outcome.Find("primary_null");
        if (nullCondition != null)
        {
            columns.Add(nullCondition);
            columnLabels.Add(L(russian, "no effect", "нет эффекта"));
        }
        foreach (double effect in BenchmarkProtocol.LocationGrid)
        {
            if (effect <= 1.0000001) continue;
            ConditionSummary? condition = outcome.Find("power_location_" + ((int)Math.Round(effect * 100)).ToString(CultureInfo.InvariantCulture));
            if (condition == null) continue;
            columns.Add(condition);
            columnLabels.Add(L(russian, "level ×", "уровень ×") + effect.ToString("0.00", CultureInfo.InvariantCulture));
        }
        foreach (double effect in BenchmarkProtocol.DispersionGrid)
        {
            ConditionSummary? condition = outcome.Find("power_dispersion_" + ((int)Math.Round(effect * 100)).ToString(CultureInfo.InvariantCulture));
            if (condition == null) continue;
            columns.Add(condition);
            columnLabels.Add(L(russian, "spread ×", "разброс ×") + effect.ToString("0.00", CultureInfo.InvariantCulture));
        }

        int metrics = AnalysisEngine.MetricKeys.Length;
        var rowLabels = new string[metrics];
        var cells = new double[metrics][];
        for (int metric = 0; metric < metrics; metric++)
        {
            rowLabels[metric] = AnalysisEngine.MetricKeys[metric].Replace('_', ' ');
            cells[metric] = new double[columns.Count];
            for (int column = 0; column < columns.Count; column++) cells[metric][column] = columns[column].MetricRate(metric);
        }

        float side = 34 * board.S;
        float bottom = board.Height - board.BottomSafe - 70 * board.S;
        Heatmap(board, new RectangleF(side, top, board.Width - 2 * side, bottom - top), rowLabels, columnLabels.ToArray(), cells);
        Footer(board, stamp, brand);
    }

    // ---------------- figure 7: the pre-registered scorecard ----------------

    private static void Verdicts(Board board, BenchmarkOutcome outcome, bool russian, string stamp, string brand)
    {
        float top = Header(board,
            L(russian, "The scorecard was written before the run", "Критерии были записаны до прогона"),
            L(russian,
                "These five thresholds are compiled into the program and hashed. Moving one to make a bad run look good changes the hash printed on every figure.",
                "Эти пять порогов вкомпилированы в программу и захешированы. Сдвинуть порог ради красивого результата — значит изменить хеш на каждом графике."));

        float side = 34 * board.S;
        float y = top;
        using var idFont = board.Typeface(15, FontStyle.Bold);
        using var questionFont = board.Typeface(12, FontStyle.Bold);
        using var detailFont = board.Typeface(10.5f);
        using var badgeFont = board.Typeface(10.5f, FontStyle.Bold);
        using var inkBrush = new SolidBrush(Ink);
        using var mutedBrush = new SolidBrush(Muted);
        using var faintPen = new Pen(Faint, 1.4f * board.S);

        float width = board.Width - 2 * side;
        foreach (HypothesisVerdict verdict in outcome.Verdicts)
        {
            Color badgeColor = verdict.Result == "pass" ? Green : verdict.Result == "fail" ? Vermillion : Orange;
            string badgeText = verdict.Result == "pass"
                ? L(russian, "PASS", "ПРОШЕЛ")
                : verdict.Result == "fail" ? L(russian, "FAIL", "ПРОВАЛ") : L(russian, "UNCLEAR", "НЕЯСНО");
            SizeF badgeSize = board.G.MeasureString(badgeText, badgeFont);
            float badgeWidth = badgeSize.Width + 26 * board.S;
            float textWidth = width - badgeWidth - 60 * board.S;

            board.G.DrawString(verdict.Id, idFont, inkBrush, side, y);
            string question = russian ? verdict.QuestionRu : verdict.Question;
            var questionRect = new RectangleF(side + 34 * board.S, y, textWidth, 200 * board.S);
            board.G.DrawString(question, questionFont, inkBrush, questionRect);
            SizeF questionSize = board.G.MeasureString(question, questionFont, (int)textWidth);
            float detailY = y + questionSize.Height + 4 * board.S;
            string detail = (russian ? verdict.ThresholdRu : verdict.Threshold) + "   —   " + verdict.Observed;
            var detailRect = new RectangleF(side + 34 * board.S, detailY, textWidth, 200 * board.S);
            board.G.DrawString(detail, detailFont, mutedBrush, detailRect);
            SizeF detailSize = board.G.MeasureString(detail, detailFont, (int)textWidth);

            Badge(board, new RectangleF(board.Width - side - badgeWidth, y + 2 * board.S, badgeWidth, badgeSize.Height + 12 * board.S), badgeText, badgeFont, badgeColor);

            y = detailY + detailSize.Height + 20 * board.S;
            board.G.DrawLine(faintPen, side, y, board.Width - side, y);
            y += 20 * board.S;
        }

        string overall = outcome.Overall == "go"
            ? L(russian, "Every pre-registered threshold was met", "Все заранее записанные пороги выполнены")
            : outcome.Overall == "no-go"
                ? L(russian, "At least one threshold was missed", "Не выполнен как минимум один порог")
                : L(russian, "Nothing failed, but not everything cleared the bar", "Провалов нет, но не всё прошло порог");
        using var overallFont = board.Typeface(14, FontStyle.Bold);
        using var overallBrush = new SolidBrush(outcome.Overall == "go" ? Green : outcome.Overall == "no-go" ? Vermillion : Orange);
        board.G.DrawString(overall, overallFont, overallBrush, new RectangleF(side, y, width, 120 * board.S));

        Footer(board, stamp, brand);
    }

    // ---------------- drawing primitives ----------------

    private sealed class Board : IDisposable
    {
        public Bitmap Bitmap { get; }
        public Graphics G { get; }
        public int Width { get; }
        public int Height { get; }
        public float S { get; }
        public int TopSafe { get; }
        public int BottomSafe { get; }

        public Board(FigureSize size)
        {
            Width = size.Width;
            Height = size.Height;
            TopSafe = size.TopSafe;
            BottomSafe = size.BottomSafe;
            S = size.Width < size.Height ? size.Width / 620f : size.Height / 780f;
            Bitmap = new Bitmap(Width, Height);
            G = Graphics.FromImage(Bitmap);
            G.SmoothingMode = SmoothingMode.AntiAlias;
            G.TextRenderingHint = System.Drawing.Text.TextRenderingHint.AntiAliasGridFit;
            G.Clear(Paper);
        }

        public Font Typeface(float points) => new Font("Segoe UI", points * S, FontStyle.Regular);

        public Font Typeface(float points, FontStyle style) => new Font("Segoe UI", points * S, style);

        public void Dispose()
        {
            G.Dispose();
            Bitmap.Dispose();
        }
    }

    private static float Header(Board board, string title, string subtitle)
    {
        float side = 34 * board.S;
        float width = board.Width - 2 * side;
        float y = board.TopSafe + 26 * board.S;
        using var titleFont = board.Typeface(22, FontStyle.Bold);
        using var subtitleFont = board.Typeface(11.5f);
        using var inkBrush = new SolidBrush(Ink);
        using var mutedBrush = new SolidBrush(Muted);
        using var rulePen = new Pen(Ink, 4 * board.S);

        board.G.DrawLine(rulePen, side, y, side + 54 * board.S, y);
        y += 18 * board.S;
        board.G.DrawString(title, titleFont, inkBrush, new RectangleF(side, y, width, 400 * board.S));
        y += board.G.MeasureString(title, titleFont, (int)width).Height + 8 * board.S;
        if (subtitle.Length > 0)
        {
            board.G.DrawString(subtitle, subtitleFont, mutedBrush, new RectangleF(side, y, width, 400 * board.S));
            y += board.G.MeasureString(subtitle, subtitleFont, (int)width).Height;
        }
        return y + 26 * board.S;
    }

    private static void Footer(Board board, string left, string right)
    {
        using var font = board.Typeface(9);
        using var brush = new SolidBrush(Muted);
        float side = 34 * board.S;
        float y = board.Height - board.BottomSafe - 30 * board.S;
        board.G.DrawString(left, font, brush, new RectangleF(side, y, board.Width - 2 * side - 220 * board.S, 60 * board.S));
        SizeF size = board.G.MeasureString(right, font);
        board.G.DrawString(right, font, brush, board.Width - side - size.Width, y);
    }

    private static void Badge(Board board, RectangleF area, string text, Font font, Color color)
    {
        using var fill = new SolidBrush(Color.FromArgb(30, color.R, color.G, color.B));
        using var pen = new Pen(color, 1.6f * board.S);
        using var brush = new SolidBrush(color);
        using GraphicsPath path = Rounded(area, 8 * board.S);
        board.G.FillPath(fill, path);
        board.G.DrawPath(pen, path);
        SizeF size = board.G.MeasureString(text, font);
        board.G.DrawString(text, font, brush, area.X + (area.Width - size.Width) / 2, area.Y + (area.Height - size.Height) / 2);
    }

    private static GraphicsPath Rounded(RectangleF area, float radius)
    {
        float r = Math.Max(1, Math.Min(radius, Math.Min(area.Width, area.Height) / 2));
        var path = new GraphicsPath();
        path.AddArc(area.X, area.Y, r * 2, r * 2, 180, 90);
        path.AddArc(area.Right - r * 2, area.Y, r * 2, r * 2, 270, 90);
        path.AddArc(area.Right - r * 2, area.Bottom - r * 2, r * 2, r * 2, 0, 90);
        path.AddArc(area.X, area.Bottom - r * 2, r * 2, r * 2, 90, 90);
        path.CloseFigure();
        return path;
    }

    private static void HorizontalBars(Board board, RectangleF plot, string[] labels, double[] values, Color[] colors, double max, double? reference, string referenceLabel)
    {
        if (labels.Length == 0) return;
        using var labelFont = board.Typeface(11);
        using var valueFont = board.Typeface(11.5f, FontStyle.Bold);
        using var noteFont = board.Typeface(9.5f);
        using var inkBrush = new SolidBrush(Ink);
        using var mutedBrush = new SolidBrush(Muted);
        using var trackBrush = new SolidBrush(Color.FromArgb(244, 245, 248));

        float labelWidth = plot.Width * .40f;
        float barLeft = plot.X + labelWidth;
        float barWidth = plot.Width - labelWidth - 96 * board.S;
        float rowHeight = plot.Height / labels.Length;
        float barHeight = Math.Min(rowHeight * .52f, 40 * board.S);
        if (max <= 0) max = 1;

        if (reference.HasValue)
        {
            float x = barLeft + (float)(Math.Clamp(reference.Value / max, 0, 1) * barWidth);
            using var pen = new Pen(Color.FromArgb(150, Ink), 1.8f * board.S) { DashStyle = DashStyle.Dash };
            board.G.DrawLine(pen, x, plot.Y, x, plot.Y + plot.Height);
            if (referenceLabel.Length > 0)
                board.G.DrawString(referenceLabel, noteFont, mutedBrush, x + 6 * board.S, plot.Y - 20 * board.S);
        }

        for (int i = 0; i < labels.Length; i++)
        {
            float centre = plot.Y + rowHeight * (i + .5f);
            var labelRect = new RectangleF(plot.X, centre - rowHeight * .45f, labelWidth - 14 * board.S, rowHeight * .9f);
            using (var format = new StringFormat { LineAlignment = StringAlignment.Center, Trimming = StringTrimming.EllipsisWord })
                board.G.DrawString(labels[i], labelFont, inkBrush, labelRect, format);

            board.G.FillRectangle(trackBrush, barLeft, centre - barHeight / 2, barWidth, barHeight);
            double value = values[i];
            if (!double.IsFinite(value))
            {
                board.G.DrawString("n/a", noteFont, mutedBrush, barLeft + 8 * board.S, centre - barHeight / 2);
                continue;
            }
            float length = (float)(Math.Clamp(value / max, 0, 1) * barWidth);
            using (var brush = new SolidBrush(colors[Math.Min(i, colors.Length - 1)]))
                board.G.FillRectangle(brush, barLeft, centre - barHeight / 2, Math.Max(length, 1.5f * board.S), barHeight);
            string text = (value * 100).ToString("0.0", CultureInfo.InvariantCulture) + "%";
            SizeF size = board.G.MeasureString(text, valueFont);
            board.G.DrawString(text, valueFont, inkBrush, barLeft + length + 10 * board.S, centre - size.Height / 2);
        }
    }

    private static void Lines(Board board, RectangleF plot, double[] xs, double[][] series, Color[] colors, double yMax, string xTitle, string yTitle, double? reference, string referenceLabel, string xFormat)
    {
        using var tickFont = board.Typeface(9.5f);
        using var titleFont = board.Typeface(10.5f);
        using var mutedBrush = new SolidBrush(Muted);
        using var gridPen = new Pen(Faint, 1.3f * board.S);
        using var axisPen = new Pen(Color.FromArgb(190, 194, 202), 1.6f * board.S);

        float left = plot.X + 62 * board.S;
        float bottom = plot.Y + plot.Height - 46 * board.S;
        float right = plot.X + plot.Width - 12 * board.S;
        float top = plot.Y + 10 * board.S;
        if (yMax <= 0) yMax = 1;

        for (int step = 0; step <= 5; step++)
        {
            double level = yMax * step / 5.0;
            float y = bottom - (float)(level / yMax) * (bottom - top);
            board.G.DrawLine(gridPen, left, y, right, y);
            string text = (level * 100).ToString(level < .1 ? "0.0" : "0", CultureInfo.InvariantCulture) + "%";
            SizeF size = board.G.MeasureString(text, tickFont);
            board.G.DrawString(text, tickFont, mutedBrush, left - size.Width - 8 * board.S, y - size.Height / 2);
        }
        board.G.DrawLine(axisPen, left, top, left, bottom);
        board.G.DrawLine(axisPen, left, bottom, right, bottom);

        double xMin = xs.Length == 0 ? 0 : xs.Min();
        double xMax = xs.Length == 0 ? 1 : xs.Max();
        if (Math.Abs(xMax - xMin) < 1e-12) xMax = xMin + 1;

        for (int i = 0; i < xs.Length; i++)
        {
            float x = left + (float)((xs[i] - xMin) / (xMax - xMin)) * (right - left);
            string text = xFormat == "0%"
                ? (xs[i] * 100).ToString("0", CultureInfo.InvariantCulture) + "%"
                : xs[i].ToString(xFormat, CultureInfo.InvariantCulture);
            SizeF size = board.G.MeasureString(text, tickFont);
            board.G.DrawString(text, tickFont, mutedBrush, x - size.Width / 2, bottom + 8 * board.S);
        }

        if (reference.HasValue && reference.Value <= yMax)
        {
            float y = bottom - (float)(reference.Value / yMax) * (bottom - top);
            using var pen = new Pen(Color.FromArgb(150, Ink), 1.8f * board.S) { DashStyle = DashStyle.Dash };
            board.G.DrawLine(pen, left, y, right, y);
            if (referenceLabel.Length > 0)
                board.G.DrawString(referenceLabel, tickFont, mutedBrush, right - 46 * board.S, y - 20 * board.S);
        }

        for (int s = 0; s < series.Length; s++)
        {
            Color color = colors[Math.Min(s, colors.Length - 1)];
            using var pen = new Pen(color, 2.6f * board.S) { LineJoin = LineJoin.Round, StartCap = LineCap.Round, EndCap = LineCap.Round };
            using var brush = new SolidBrush(color);
            var points = new List<PointF>();
            for (int i = 0; i < xs.Length && i < series[s].Length; i++)
            {
                if (!double.IsFinite(series[s][i])) continue;
                float x = left + (float)((xs[i] - xMin) / (xMax - xMin)) * (right - left);
                float y = bottom - (float)(Math.Clamp(series[s][i] / yMax, 0, 1)) * (bottom - top);
                points.Add(new PointF(x, y));
            }
            if (points.Count >= 2) board.G.DrawLines(pen, points.ToArray());
            float radius = 4.2f * board.S;
            foreach (PointF point in points)
                board.G.FillEllipse(brush, point.X - radius, point.Y - radius, radius * 2, radius * 2);
        }

        if (xTitle.Length > 0)
        {
            SizeF size = board.G.MeasureString(xTitle, titleFont);
            board.G.DrawString(xTitle, titleFont, mutedBrush, left + (right - left - size.Width) / 2, bottom + 26 * board.S);
        }
        if (yTitle.Length > 0)
            board.G.DrawString(yTitle, titleFont, mutedBrush, left, top - 4 * board.S);
    }

    private static void Scatter(Board board, RectangleF plot, string[] names, double[] xs, double[] ys, Color[] colors, double xMax, double yMax, string xTitle, string yTitle, double? verticalReference, string referenceLabel)
    {
        using var tickFont = board.Typeface(9.5f);
        using var titleFont = board.Typeface(10.5f);
        using var labelFont = board.Typeface(10, FontStyle.Bold);
        using var mutedBrush = new SolidBrush(Muted);
        using var gridPen = new Pen(Faint, 1.3f * board.S);
        using var axisPen = new Pen(Color.FromArgb(190, 194, 202), 1.6f * board.S);

        float left = plot.X + 62 * board.S;
        float bottom = plot.Y + plot.Height - 48 * board.S;
        float right = plot.X + plot.Width - 14 * board.S;
        float top = plot.Y + 12 * board.S;
        if (xMax <= 0) xMax = 1;
        if (yMax <= 0) yMax = 1;

        for (int step = 0; step <= 5; step++)
        {
            double level = yMax * step / 5.0;
            float y = bottom - (float)(level / yMax) * (bottom - top);
            board.G.DrawLine(gridPen, left, y, right, y);
            string text = (level * 100).ToString("0", CultureInfo.InvariantCulture) + "%";
            SizeF size = board.G.MeasureString(text, tickFont);
            board.G.DrawString(text, tickFont, mutedBrush, left - size.Width - 8 * board.S, y - size.Height / 2);
        }
        for (int step = 0; step <= 4; step++)
        {
            double level = xMax * step / 4.0;
            float x = left + (float)(level / xMax) * (right - left);
            board.G.DrawLine(gridPen, x, top, x, bottom);
            string text = (level * 100).ToString("0.0", CultureInfo.InvariantCulture) + "%";
            SizeF size = board.G.MeasureString(text, tickFont);
            board.G.DrawString(text, tickFont, mutedBrush, x - size.Width / 2, bottom + 8 * board.S);
        }
        board.G.DrawLine(axisPen, left, top, left, bottom);
        board.G.DrawLine(axisPen, left, bottom, right, bottom);

        if (verticalReference.HasValue && verticalReference.Value <= xMax)
        {
            float x = left + (float)(verticalReference.Value / xMax) * (right - left);
            using var pen = new Pen(Color.FromArgb(150, Ink), 1.8f * board.S) { DashStyle = DashStyle.Dash };
            board.G.DrawLine(pen, x, top, x, bottom);
            if (referenceLabel.Length > 0)
                board.G.DrawString(referenceLabel, tickFont, mutedBrush, x + 6 * board.S, top);
        }

        for (int i = 0; i < names.Length && i < xs.Length && i < ys.Length; i++)
        {
            Color color = colors[Math.Min(i, colors.Length - 1)];
            using var brush = new SolidBrush(color);
            float x = left + (float)(Math.Clamp(xs[i] / xMax, 0, 1)) * (right - left);
            float y = bottom - (float)(Math.Clamp(ys[i] / yMax, 0, 1)) * (bottom - top);
            float radius = 7.5f * board.S;
            board.G.FillEllipse(brush, x - radius, y - radius, radius * 2, radius * 2);
            SizeF size = board.G.MeasureString(names[i], labelFont);
            float labelX = x + radius + 7 * board.S;
            if (labelX + size.Width > right) labelX = x - radius - 7 * board.S - size.Width;
            board.G.DrawString(names[i], labelFont, brush, labelX, y - size.Height / 2);
        }

        if (xTitle.Length > 0)
        {
            SizeF size = board.G.MeasureString(xTitle, titleFont);
            board.G.DrawString(xTitle, titleFont, mutedBrush, left + (right - left - size.Width) / 2, bottom + 26 * board.S);
        }
        if (yTitle.Length > 0)
            board.G.DrawString(yTitle, titleFont, mutedBrush, left, top - 6 * board.S);
    }

    private static void Histogram(Board board, RectangleF plot, double[] values, int bins, double min, double max, Color color, string xTitle, string yTitle)
    {
        using var tickFont = board.Typeface(9.5f);
        using var titleFont = board.Typeface(10.5f);
        using var mutedBrush = new SolidBrush(Muted);
        using var brush = new SolidBrush(color);
        using var gridPen = new Pen(Faint, 1.3f * board.S);
        using var axisPen = new Pen(Color.FromArgb(190, 194, 202), 1.6f * board.S);

        float left = plot.X + 50 * board.S;
        float bottom = plot.Y + plot.Height - 48 * board.S;
        float right = plot.X + plot.Width - 12 * board.S;
        float top = plot.Y + 12 * board.S;

        var counts = new int[Math.Max(1, bins)];
        int used = 0;
        foreach (double value in values)
        {
            if (!double.IsFinite(value)) continue;
            int bin = (int)Math.Floor((value - min) / (max - min) * counts.Length);
            counts[Math.Clamp(bin, 0, counts.Length - 1)]++;
            used++;
        }
        int peak = 1;
        foreach (int count in counts) if (count > peak) peak = count;

        for (int step = 0; step <= 4; step++)
        {
            float y = bottom - (bottom - top) * step / 4f;
            board.G.DrawLine(gridPen, left, y, right, y);
            string text = ((int)Math.Round(peak * step / 4.0)).ToString(CultureInfo.InvariantCulture);
            SizeF size = board.G.MeasureString(text, tickFont);
            board.G.DrawString(text, tickFont, mutedBrush, left - size.Width - 8 * board.S, y - size.Height / 2);
        }
        board.G.DrawLine(axisPen, left, top, left, bottom);
        board.G.DrawLine(axisPen, left, bottom, right, bottom);

        float slot = (right - left) / counts.Length;
        for (int i = 0; i < counts.Length; i++)
        {
            float height = (bottom - top) * counts[i] / peak;
            board.G.FillRectangle(brush, left + slot * i + slot * .12f, bottom - height, slot * .76f, height);
        }

        for (int step = 0; step <= 4; step++)
        {
            double level = min + (max - min) * step / 4.0;
            float x = left + (right - left) * step / 4f;
            string text = level.ToString("0.0", CultureInfo.InvariantCulture);
            SizeF size = board.G.MeasureString(text, tickFont);
            board.G.DrawString(text, tickFont, mutedBrush, x - size.Width / 2, bottom + 8 * board.S);
        }

        if (xTitle.Length > 0)
        {
            SizeF size = board.G.MeasureString(xTitle, titleFont);
            board.G.DrawString(xTitle, titleFont, mutedBrush, left + (right - left - size.Width) / 2, bottom + 26 * board.S);
        }
        if (yTitle.Length > 0)
            board.G.DrawString(yTitle + "  (n = " + used.ToString(CultureInfo.InvariantCulture) + ")", titleFont, mutedBrush, left, top - 6 * board.S);
    }

    private static void Heatmap(Board board, RectangleF plot, string[] rowLabels, string[] columnLabels, double[][] cells)
    {
        if (rowLabels.Length == 0 || columnLabels.Length == 0) return;
        using var labelFont = board.Typeface(9.5f);
        using var valueFont = board.Typeface(9.5f, FontStyle.Bold);
        using var inkBrush = new SolidBrush(Ink);
        using var mutedBrush = new SolidBrush(Muted);
        using var whiteBrush = new SolidBrush(Paper);

        float labelWidth = 150 * board.S;
        float headerHeight = 56 * board.S;
        float gridLeft = plot.X + labelWidth;
        float gridTop = plot.Y + headerHeight;
        float cellWidth = (plot.X + plot.Width - gridLeft) / columnLabels.Length;
        float cellHeight = (plot.Y + plot.Height - gridTop) / rowLabels.Length;

        for (int column = 0; column < columnLabels.Length; column++)
        {
            var area = new RectangleF(gridLeft + cellWidth * column, plot.Y, cellWidth, headerHeight - 8 * board.S);
            using var format = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Far };
            board.G.DrawString(columnLabels[column], labelFont, mutedBrush, area, format);
        }

        for (int row = 0; row < rowLabels.Length; row++)
        {
            var area = new RectangleF(plot.X, gridTop + cellHeight * row, labelWidth - 12 * board.S, cellHeight);
            using var format = new StringFormat { Alignment = StringAlignment.Far, LineAlignment = StringAlignment.Center, Trimming = StringTrimming.EllipsisWord };
            board.G.DrawString(rowLabels[row], labelFont, inkBrush, area, format);

            for (int column = 0; column < columnLabels.Length; column++)
            {
                double value = cells[row][column];
                var cell = new RectangleF(gridLeft + cellWidth * column + 1.5f * board.S, gridTop + cellHeight * row + 1.5f * board.S,
                    cellWidth - 3 * board.S, cellHeight - 3 * board.S);
                if (!double.IsFinite(value))
                {
                    using var faint = new SolidBrush(Color.FromArgb(246, 247, 249));
                    board.G.FillRectangle(faint, cell);
                    continue;
                }
                double intensity = Math.Clamp(value, 0, 1);
                int red = (int)Math.Round(255 - (255 - Blue.R) * intensity);
                int green = (int)Math.Round(255 - (255 - Blue.G) * intensity);
                int blue = (int)Math.Round(255 - (255 - Blue.B) * intensity);
                using var fill = new SolidBrush(Color.FromArgb(Math.Clamp(red, 0, 255), Math.Clamp(green, 0, 255), Math.Clamp(blue, 0, 255)));
                board.G.FillRectangle(fill, cell);
                string text = (value * 100).ToString("0", CultureInfo.InvariantCulture);
                SizeF size = board.G.MeasureString(text, valueFont);
                board.G.DrawString(text, valueFont, intensity > .55 ? whiteBrush : inkBrush,
                    cell.X + (cell.Width - size.Width) / 2, cell.Y + (cell.Height - size.Height) / 2);
            }
        }
    }

    private static void Legend(Board board, RectangleF area, string[] names, Color[] colors)
    {
        using var font = board.Typeface(10);
        using var brush = new SolidBrush(Ink);
        float x = area.X;
        float y = area.Y;
        float lineHeight = 26 * board.S;
        for (int i = 0; i < names.Length; i++)
        {
            SizeF size = board.G.MeasureString(names[i], font);
            float itemWidth = size.Width + 34 * board.S;
            if (x + itemWidth > area.X + area.Width)
            {
                x = area.X;
                y += lineHeight;
            }
            using var swatch = new SolidBrush(colors[Math.Min(i, colors.Length - 1)]);
            float dot = 9 * board.S;
            board.G.FillEllipse(swatch, x, y + size.Height / 2 - dot / 2, dot, dot);
            board.G.DrawString(names[i], font, brush, x + dot + 7 * board.S, y);
            x += itemWidth;
        }
    }

    private static double NiceCeiling(double value)
    {
        if (!double.IsFinite(value) || value <= 0) return .1;
        double[] steps = { .05, .075, .1, .15, .2, .25, .3, .4, .5, .75, 1 };
        foreach (double step in steps) if (value <= step) return step;
        return 1;
    }
}
