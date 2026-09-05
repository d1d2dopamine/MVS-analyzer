namespace MvsAnalyzer;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        // Checked before any window exists, so a reviewer or a build server can run the benchmark headless.
        if (Benchmarking.BenchmarkCommandLine.Handles(args)) return Benchmarking.BenchmarkCommandLine.Run(args);
        ApplicationConfiguration.Initialize();
        // A stray exception now shows a message instead of killing the process.
        Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
        Application.ThreadException += (_, e) => MessageBox.Show(e.Exception.Message, "MVS Analyzer", MessageBoxButtons.OK, MessageBoxIcon.Error);
        AppDomain.CurrentDomain.UnhandledException += (_, e) => MessageBox.Show((e.ExceptionObject as Exception)?.Message ?? "Unknown error", "MVS Analyzer", MessageBoxButtons.OK, MessageBoxIcon.Error);
        AppSettings settings = AppSettings.Load();
        string marker = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MVS_Analyzer", "language.txt");
        if (!File.Exists(marker))
        {
            using var dialog = new LanguageDialog();
            if (dialog.ShowDialog() != DialogResult.OK) return 0;
            settings.Language = dialog.LanguageCode; settings.Save();
            Directory.CreateDirectory(Path.GetDirectoryName(marker)!); File.WriteAllText(marker, settings.Language);
        }
        Application.Run(new MainForm(settings));
        return 0;
    }
}

internal sealed class LanguageDialog : Form
{
    private readonly ComboBox combo = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 310 };
    public string LanguageCode { get; private set; } = "en";
    public LanguageDialog()
    {
        Text = "MVS Analyzer — Language"; StartPosition = FormStartPosition.CenterScreen; AutoScaleMode = AutoScaleMode.Dpi; ClientSize = new Size(520, 230);
        FormBorderStyle = FormBorderStyle.FixedDialog; MaximizeBox = false; MinimizeBox = false; Font = new Font("Segoe UI", 10);
        Controls.Add(new Label { Text = "Choose your language", Font = new Font("Segoe UI", 17, FontStyle.Bold), AutoSize = true, Location = new Point(28, 24) });
        Controls.Add(new Label { Text = "English and Russian are currently complete. This can be changed in Settings.", AutoSize = true, Location = new Point(30, 68), ForeColor = Color.DimGray });
        combo.Items.AddRange(new object[] { "English", "Русский" }); combo.SelectedIndex = 0; combo.Location = new Point(30, 105); Controls.Add(combo);
        var ok = new Button { Text = "Continue", Width = 130, Height = 38, Location = new Point(30, 158) };
        ok.Click += (_, _) => { LanguageCode = combo.SelectedIndex == 1 ? "ru" : "en"; DialogResult = DialogResult.OK; Close(); }; Controls.Add(ok);
    }
}
