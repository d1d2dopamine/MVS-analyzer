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
        string[] pages = { "home", "project", "data", "calibration", "analysis", "colab", "results", "figures", "outputs", "history", "audit", "plugins", "settings", "help", "advanced" };
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
                    if (page is "colab" or "results" or "advanced" or "calibration" or "settings")
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
                foreach (string page in new[] { "calibration", "analysis", "colab", "results" })
                {
                    form.ShowLayoutFixture(page, populated: false); Application.DoEvents(); checkedViews++;
                    failures += form.InspectLayout().Count;
                }
            }
            form.Close();
        }
        if (!ColabBridge.AllowedOrigin("https://colab.research.google.com") || ColabBridge.AllowedOrigin("https://evil.example") ||
            ColabBridge.AllowedOrigin("http://colab.research.google.com")) { Console.WriteLine("FAIL Colab origin boundary"); failures++; }
        Console.WriteLine($"Windows layout views: {checkedViews}; failures: {failures}. Screenshots require human review: {output}");
        Console.WriteLine("These checks do not validate statistical results or all real-monitor DPI transitions.");
        return failures == 0 ? 0 : 1;
    }
}
