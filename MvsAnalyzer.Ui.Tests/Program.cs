using System.Drawing;
using System.Drawing.Imaging;
using System.Windows.Forms;
using MvsAnalyzer;

internal static class UiChecks
{
    [STAThread]
    private static int Main(string[] args)
    {
        Application.SetHighDpiMode(HighDpiMode.PerMonitorV2);
        Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
        string output = args.Length > 0 ? Path.GetFullPath(args[0]) : Path.GetFullPath("artifacts/ui-layout");
        Directory.CreateDirectory(output);
        string[] pages = { "home", "project", "data", "calibration", "analysis", "results", "figures", "outputs", "history", "audit", "plugins", "settings", "help", "advanced" };
        int failures = 0, checkedViews = 0;
        foreach (string language in new[] { "en", "ru" })
        foreach (string theme in new[] { "light", "dark" })
        foreach (string mode in new[] { "guided", "expert" })
        {
            using var form = new MainForm(new AppSettings { Language = language, Theme = theme, InterfaceMode = mode }, layoutTest: true);
            form.Show(); Application.DoEvents();
            foreach (Size size in new[] { new Size(1040, 680), new Size(1240, 780), new Size(1600, 1000) })
            {
                form.ClientSize = size; Application.DoEvents();
                foreach (string page in pages)
                {
                    form.ShowLayoutFixture(page); form.PerformLayout(); Application.DoEvents(); checkedViews++;
                    foreach (string failure in form.InspectLayout())
                    { Console.WriteLine($"FAIL {language}/{theme}/{size}/{page}: {failure}"); failures++; }
                    if (page is "home" or "results" or "advanced" or "calibration" or "settings")
                    {
                        using var bitmap = new Bitmap(form.Width, form.Height);
                        form.DrawToBitmap(bitmap, new Rectangle(Point.Empty, bitmap.Size));
                        bitmap.Save(Path.Combine(output, $"{language}_{theme}_{mode}_{size.Width}_{page}.png"), ImageFormat.Png);
                    }
                    if (page == "results")
                    foreach (TabControl tabs in form.LayoutTabs())
                    for (int index = 0; index < tabs.TabCount; index++)
                    {
                        tabs.SelectedIndex = index; Application.DoEvents();
                        foreach (DataGridView grid in tabs.SelectedTab!.Controls.OfType<DataGridView>())
                            if (grid.Width < 300 || grid.Height < 200) { Console.WriteLine("FAIL collapsed metric grid"); failures++; }
                    }
                }
                foreach (string page in new[] { "calibration", "analysis", "results" })
                {
                    form.ShowLayoutFixture(page, populated: false); Application.DoEvents(); checkedViews++;
                    failures += form.InspectLayout().Count;
                }
            }
            foreach (Size popupSize in new[] { new Size(540, 460), new Size(620, 650), new Size(800, 800) })
            foreach (string phase in new[] { "offline", "preparing", "ready", "calibrating", "calibrated", "analyzing", "complete", "failed" })
            {
                Form window = form.ShowColabLayoutFixture(phase); window.ClientSize = popupSize; Application.DoEvents(); checkedViews++;
                foreach (string failure in form.InspectColabLayout()) { Console.WriteLine($"FAIL Colab {language}/{theme}/{popupSize}/{phase}: {failure}"); failures++; }
                using var bitmap = new Bitmap(window.Width, window.Height);
                window.DrawToBitmap(bitmap, new Rectangle(Point.Empty, bitmap.Size));
                bitmap.Save(Path.Combine(output, $"{language}_{theme}_{mode}_{popupSize.Width}_colab_{phase}.png"), ImageFormat.Png);
                if (!ReferenceEquals(window, form.ShowColabLayoutFixture(phase))) { Console.WriteLine("FAIL duplicate Colab window"); failures++; }
                form.ShowLayoutFixture("home"); Application.DoEvents();
                if (window.IsDisposed) { Console.WriteLine("FAIL navigation closed Colab window"); failures++; }
                window.Close(); Application.DoEvents();
            }
            Task modal = form.ExerciseProgressLayoutAsync(progress =>
            {
                using var background = new Bitmap(form.Width, form.Height);
                form.DrawToBitmap(background, new Rectangle(Point.Empty, background.Size));
                background.Save(Path.Combine(output, $"{language}_{theme}_{mode}_busy_main.png"), ImageFormat.Png);
                using var image = new Bitmap(progress.Width, progress.Height);
                progress.DrawToBitmap(image, new Rectangle(Point.Empty, image.Size));
                image.Save(Path.Combine(output, $"{language}_{theme}_{mode}_progress.png"), ImageFormat.Png);
            });
            while (!modal.IsCompleted) { Application.DoEvents(); Thread.Sleep(5); }
            try { modal.GetAwaiter().GetResult(); }
            catch (Exception error) { Console.WriteLine("FAIL modal theme: " + error.Message); failures++; }
            Task cancellation = form.ExerciseProgressLayoutAsync(_ => { }, cancel: true);
            while (!cancellation.IsCompleted) { Application.DoEvents(); Thread.Sleep(5); }
            try { cancellation.GetAwaiter().GetResult(); Console.WriteLine("FAIL cancellation was ignored"); failures++; }
            catch (OperationCanceledException) { }
            if (!form.Enabled) { Console.WriteLine("FAIL main form not enabled after cancellation"); failures++; }
            form.Close();
        }
        foreach (string kind in new[] { "variance", "melsm", "estimation", "benchmark" })
            if (MainForm.NormalizeColabAction(kind, kind) != "analyze") { Console.WriteLine("FAIL additional method command"); failures++; }
        if (MainForm.NormalizeColabAction("calibrate", "standard") != "calibrate") failures++;
        if (MainForm.NormalizeColabAction("prepare", "standard") != "prepare") failures++;
        if (!ColabBridge.AllowedOrigin("https://colab.research.google.com") || ColabBridge.AllowedOrigin("https://evil.example") ||
            ColabBridge.AllowedOrigin("http://colab.research.google.com")) { Console.WriteLine("FAIL Colab origin boundary"); failures++; }
        Console.WriteLine($"Windows layout views: {checkedViews}; failures: {failures}. Screenshots require human review: {output}");
        Console.WriteLine("These checks do not validate statistical results or all real-monitor DPI transitions.");
        return failures == 0 ? 0 : 1;
    }
}
