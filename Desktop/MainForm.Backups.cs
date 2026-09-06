using System.Globalization;
namespace MvsAnalyzer;
internal sealed partial class MainForm
{
    private void AddBackupCard(FlowLayoutPanel page)
    {
        var restore = Button(T("Load backup and continue", "Загрузить бэкап и продолжить"), true, 340);
        restore.Height = 46; restore.Click += async (_, _) => await LoadBackupAndContinueAsync();
        var open = Button(T("Open backups folder", "Открыть папку бэкапов"), false, 290);
        open.Height = 46; open.Click += (_, _) => { Directory.CreateDirectory(BackupSession.Folder); OpenFolder(BackupSession.Folder); };
        var export = Button(T("Save all backups as ZIP", "Сохранить все бэкапы в ZIP"), false, 310); export.Height = 46;
        export.Click += async (_, _) =>
        {
            using var dialog = new SaveFileDialog { Filter = "ZIP (*.zip)|*.zip", FileName = "MVS_Backups.zip", OverwritePrompt = true };
            if (dialog.ShowDialog(this) != DialogResult.OK) return;
            try { await Task.Run(() => BackupSession.ExportAll(dialog.FileName)); }
            catch (Exception error) { MessageBox.Show(this, error.Message, "MVS", MessageBoxButtons.OK, MessageBoxIcon.Warning); }
        };
        page.Controls.Add(FlowCard(T("Backups and offline continuation", "Бэкапы и продолжение оффлайн"),
            T("All checkpoints are in one MVS_Backups folder and MVS_Backups.zip. Colab sends fresh copies here while MVS and its browser tab stay connected. Backups contain input data: keep them private. Unfinished work after the last checkpoint is repeated.",
              "Все контрольные точки — в одной папке MVS_Backups и архиве MVS_Backups.zip. Colab передаёт свежие копии сюда, пока MVS и вкладка браузера подключены. Бэкапы содержат данные: храните их конфиденциально. При продолжении повторяется только работа после последней сохранённой точки."),
            new ActionButtonPanel(false, 1, restore, open, export)));
    }
    private async Task LoadBackupAndContinueAsync()
    {
        if (localOperationInProgress) { MessageBox.Show(this, T("Wait for the current local calculation.", "Дождитесь текущего локального расчёта.")); return; }
        using var source = new OpenFileDialog { Filter = "MVS backups (*.zip;*.mvsbackup)|*.zip;*.mvsbackup", Title = T("Load backup and continue", "Загрузить бэкап и продолжить") };
        if (source.ShowDialog(this) != DialogResult.OK) return;
        try
        {
            List<BackupDocument> backups = await Task.Run(() => BackupSession.ReadArchive(source.FileName));
            BackupDocument? selected = ChooseBackup(backups); if (selected == null) return;
            string question = T("Continue from the last saved checkpoint?", "Продолжить с места, на котором остановились?") + "\n\n" + BackupLabel(selected) + "\n\n" +
                T("Existing result files will not be replaced. Work after the last saved checkpoint is repeated. Stop the original Colab process before continuing here. Floating-point results can differ across operating systems.",
                  "Существующие файлы результатов не будут заменены. Работа после последней сохранённой точки повторится. Перед продолжением здесь остановите прежний процесс Colab. Между операционными системами возможны различия округления.");
            if (MessageBox.Show(this, question, T("Continue offline", "Продолжить оффлайн"), MessageBoxButtons.YesNo, MessageBoxIcon.Question, MessageBoxDefaultButton.Button2) != DialogResult.Yes) return;
            using var destination = new FolderBrowserDialog { Description = T("Choose where to save the resumed result", "Выберите папку для результата продолженного расчёта") };
            if (destination.ShowDialog(this) != DialogResult.OK) return;
            using var progress = new ProgressDialog(T("Continuing from backup", "Продолжение из бэкапа"), T("Cancel", "Отмена"), settings.Language == "ru");
            BackupRunResult? outcome = null;
            await RunLocalTaskAsync(progress, async () =>
            {
                var reporter = new Progress<ProgressInfo>(progress.UpdateProgress);
                outcome = await Task.Run(() => BackupRunner.Run(selected, destination.SelectedPath, reporter, progress.Token, settings.Language == "ru"));
            });
            if (outcome == null) return;
            if (outcome.Data != null && outcome.State != null)
            {
                CalibrationPersistence.Apply(outcome.State, settings); settings.Save();
                data = outcome.Data; calibration = outcome.Calibration; results = outcome.Results;
                datasetPath = ""; datasetName = outcome.State.Dataset; datasetHash = outcome.State.DatasetHash;
                projectName = selected.Request.Context?.Project ?? "Restored project"; projectDescription = selected.Request.Context?.Description ?? "";
                calibrationSource = outcome.State.CalibrationSource; lastCalibrationRepetitions = selectedCalibrationRepetitions = outcome.State.Repetitions;
                loadedProcessing = ProcessingSnapshot.From(settings); calibrationSettingsHash = SettingsContract.Fingerprint(settings);
                analysisHalf = settings.SplitCalibration ? AnalysisEngine.SplitEntities(data, settings.CalibrationSeed).Analysis : null;
                lastArtifacts.Clear(); lastFigureFiles.Clear(); Navigate(results == null ? "calibration" : "results");
            }
            else { lastScienceFolder = outcome.Folder; if (selected.Request.Kind == "benchmark") lastBenchmarkFolder = outcome.Folder; }
            MessageBox.Show(this, T("Resumed calculation saved. ", "Продолженный расчёт сохранён. ") +
                (outcome.ExitCode == 2 ? T("Some diagnostics did not pass; inspect the report.\n", "Некоторые диагностики не пройдены; проверьте отчёт.\n") : "\n") + outcome.Folder, "MVS", MessageBoxButtons.OK, MessageBoxIcon.Information);
            OpenFolder(outcome.Folder);
        }
        catch (OperationCanceledException) { MessageBox.Show(this, T("Stopped. The latest checkpoint remains in MVS_Backups.", "Остановлено. Последняя контрольная точка осталась в MVS_Backups.")); }
        catch (Exception error) { MessageBox.Show(this, error.Message, "MVS", MessageBoxButtons.OK, MessageBoxIcon.Warning); }
    }
    private string BackupLabel(BackupDocument b) => b.Request.Kind + " · " + b.SavedUtc.ToLocalTime().ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture) +
        " · " + b.Units.Count.ToString(CultureInfo.InvariantCulture) + T(" saved blocks", " сохранённых блоков") +
        (b.CalculationComplete ? T(" · calculation complete", " · расчёт завершён") : "");
    private BackupDocument? ChooseBackup(List<BackupDocument> backups)
    {
        if (backups.Count == 0) throw new InvalidDataException(T("No backups found.", "Бэкапы не найдены."));
        if (backups.Count == 1) return backups[0];
        using var chooser = new Form { Text = T("Choose a checkpoint", "Выберите контрольную точку"), StartPosition = FormStartPosition.CenterParent,
            ClientSize = new Size(800, 380), MinimumSize = new Size(650, 320), Font = Font, BackColor = Surface, ForeColor = TextColor, MinimizeBox = false, MaximizeBox = false };
        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(16), ColumnCount = 1, RowCount = 3 };
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize)); layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100)); layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 60));
        layout.Controls.Add(new Label { Text = T("Newest first. Previous snapshots are retained for recovery.", "Сначала новые. Предыдущие копии оставлены для восстановления."), AutoSize = true, Margin = new Padding(0, 0, 0, 12) }, 0, 0);
        var list = new ListBox { Dock = DockStyle.Fill, HorizontalScrollbar = true, BackColor = Surface, ForeColor = TextColor, IntegralHeight = false };
        foreach (var backup in backups) list.Items.Add(BackupLabel(backup)); list.SelectedIndex = 0; layout.Controls.Add(list, 0, 1);
        var choose = Button(T("Choose", "Выбрать"), true, 200); choose.Dock = DockStyle.Right; choose.Margin = new Padding(0, 12, 0, 0);
        choose.Click += (_, _) => chooser.DialogResult = DialogResult.OK; layout.Controls.Add(choose, 0, 2); chooser.Controls.Add(layout); chooser.AcceptButton = choose;
        return chooser.ShowDialog(this) == DialogResult.OK ? backups[list.SelectedIndex] : null;
    }
}
