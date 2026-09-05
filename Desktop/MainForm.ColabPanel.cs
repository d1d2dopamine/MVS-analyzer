using System.IO.Compression;

namespace MvsAnalyzer;

internal sealed partial class MainForm
{
    private sealed record ColabPanelView(string Key, Label State, Label Detail, Label Runtime, ProgressBar Progress,
        Button Calibrate, Button Analyze, Button Download, Button Stop, Button Code, Button Reconnect, Button Disconnect);
    private ColabPanelView? colabPanel;

    private void ShowColabPanel(string? key = null)
    {
        if (key != null) colabPanelKey = key;
        else if (!layoutTestMode && colabPanelKey.Length == 0)
            colabPanelKey = Sessions.Latest()?.Key ?? "";
        Navigate("colab");
    }
    private Panel ColabActions(params Button[] buttons)
    {
        var panel = new Panel { Height = 52, Margin = new Padding(0, 0, 0, 4) };
        panel.Controls.AddRange(buttons);
        bool arranging = false;
        void Arrange()
        {
            if (arranging || panel.IsDisposed) return;
            arranging = true;
            try
            {
                int x = 0, y = 0, rowHeight = 0;
                foreach (Button button in buttons)
                {
                    int width = Math.Min(Math.Max(180, button.MinimumSize.Width), Math.Max(120, panel.ClientSize.Width));
                    if (x > 0 && x + width > panel.ClientSize.Width) { x = 0; y += rowHeight + 10; rowHeight = 0; }
                    int height = Math.Max(44, WrappedHeight(button, width - 20) + 12);
                    button.SetBounds(x, y, width, height); x += width + 10; rowHeight = Math.Max(rowHeight, height);
                }
                panel.Height = y + rowHeight;
            }
            finally { arranging = false; }
        }
        panel.SizeChanged += (_, _) => Arrange(); panel.Layout += (_, _) => Arrange(); Arrange();
        return panel;
    }
    private Button ColabPanelButton(string en, string ru, Action action, bool primary = false, int width = 205)
    {
        var button = Button(T(en, ru), primary, width);
        button.Height = 44; button.MinimumSize = new Size(width, 44); button.AccessibleName = button.Text;
        button.Click += (_, _) => { try { action(); } catch (Exception error) { ColabWarning(error.Message); } };
        return button;
    }
    private void ShowColab()
    {
        if (!layoutTestMode && colabPanelKey.Length == 0) colabPanelKey = Sessions.Latest()?.Key ?? "";
        string key = colabPanelKey;
        var page = Page("Google Colab", T("Connection, computation and results — in one place.", "Подключение, расчёт и результаты — в одном месте."));
        var state = new Label { Text = T("Not connected", "Не подключено"), Font = new Font(Font, FontStyle.Bold), ForeColor = TextColor };
        var detail = new Label { Text = T("Prepare a job from your data, then run the first notebook cell once.", "Подготовьте задание из ваших данных и один раз запустите первую ячейку блокнота."), ForeColor = Secondary };
        var runtime = new Label { Text = T("Runtime has not reported yet.", "Среда выполнения ещё не сообщила о себе."), ForeColor = Secondary };
        var progress = new ProgressBar { Height = 22, Minimum = 0, Maximum = 100, Value = 0, AccessibleName = T("Colab progress", "Прогресс Colab") };
        var calibrate = ColabPanelButton("Calibrate", "Калибровать", () => RunColabPanelAction("calibrate"), true);
        var analyze = ColabPanelButton("Analyze", "Анализировать", () => RunColabPanelAction("analyze"), true);
        var download = ColabPanelButton("Download results", "Скачать результаты", () => RunColabPanelAction("download"));
        var stop = ColabPanelButton("Stop", "Остановить", () => RunColabPanelAction("cancel"));
        page.Controls.Add(FlowCard(T("Job status", "Состояние задания"), "", state, runtime, progress, detail,
            ColabActions(calibrate, analyze, download, stop)));

        var code = ColabPanelButton("Connection code…", "Код подключения…", () => ShowColabConnection(key));
        var open = ColabPanelButton("Open notebook", "Открыть блокнот", () => OpenBrowser(Sessions.NotebookFor(key.Length == 0 ? null : key)));
        var reconnect = ColabPanelButton("Reconnect", "Переподключить", () => ReconnectColab(key));
        var disconnect = ColabPanelButton("Disconnect", "Отключить связь", () => DisconnectColab(key));
        var runtimeButton = ColabPanelButton("Select runtime…", "Выбрать среду…", () => SelectColabRuntime(key));
        var export = ColabPanelButton("Save job ZIP…", "Сохранить ZIP задания…", () => SaveColabJob(key));
        var import = ColabPanelButton("Import results…", "Импорт результатов…", ImportColabBundle);
        var prepare = ColabPanelButton("Use current data", "Задание из текущих данных", () => StartColab("calibrate", selectedCalibrationRepetitions));
        prepare.Enabled = data != null;
        var notebook = ColabPanelButton("Save updated notebook…", "Сохранить новый блокнот…", SaveShippedColabNotebook);
        page.Controls.Add(FlowCard(T("Connection and recovery", "Подключение и восстановление"), T(
            "No new copy is required. Reopen the same notebook. Reconnect revokes the old code but preserves verified calibration and received results.",
            "Новая копия не требуется — открывайте тот же блокнот. Переподключение отзывает старый код, но сохраняет проверенную калибровку и полученные результаты."),
            ColabActions(open, code, runtimeButton), ColabActions(reconnect, disconnect, export), ColabActions(prepare, import, notebook)));
        page.Controls.Add(FlowCard(T("Three steps", "Три шага"), T(
            "1. Choose a Colab runtime in the notebook; CPU is sufficient for this engine.\n2. Paste the connection code into the first cell and leave it running as the controller.\n3. Use Calibrate → Analyze → Download results here. Percentages come from the CLI; preparation uses an indeterminate indicator.\nIf the tab closes, the connection expires within about 45 seconds after the last status. This does not mean the cloud process was stopped.",
            "1. Выберите среду в меню блокнота Colab; для этого движка достаточно CPU.\n2. Вставьте код в первую ячейку и оставьте её работающей как контроллер.\n3. Нажимайте здесь «Калибровать» → «Анализировать» → «Скачать результаты». Проценты поступают от CLI; на подготовке показывается индикатор без процентов.\nПосле закрытия вкладки связь истекает примерно через 45 секунд с последнего сообщения. Это не означает остановку облачного процесса.")));
        var view = new ColabPanelView(key, state, detail, runtime, progress, calibrate, analyze, download, stop, code, reconnect, disconnect);
        colabPanel = view;
        var timer = new System.Windows.Forms.Timer { Interval = 1000 };
        timer.Tick += (_, _) => RefreshColabPanel();
        page.Disposed += (_, _) => { timer.Stop(); timer.Dispose(); if (ReferenceEquals(colabPanel, view)) colabPanel = null; };
        if (!layoutTestMode) { RefreshColabPanel(); timer.Start(); }
    }
    private string ColabPhaseLabel(string phase) => phase switch
    {
        "opening" => T("Waiting for connection", "Ожидание подключения"),
        "preparing" => T("Preparing runtime", "Подготовка среды"),
        "ready" => T("Ready for commands", "Готово к командам"),
        "calibrating" => T("Calibrating", "Калибровка"),
        "analyzing" or "running" => T("Analyzing", "Анализ"),
        "calibrated" => T("Calibration ready", "Калибровка готова"),
        "complete" => T("Results ready", "Результаты готовы"),
        "downloading" => T("Downloading", "Скачивание"),
        "cancelling" => T("Stopping — awaiting confirmation", "Остановка — ожидается подтверждение"),
        "cancelled" => T("Stopped", "Остановлено"),
        "failed" => T("Job failed — see details", "Ошибка задания — см. подробности"),
        _ => T("Not connected", "Нет подключения")
    };
    private ColabRunPlan? ReadOnlyColabPlan(string key)
    {
        if (colabPlans.TryGetValue(key, out var prepared)) return prepared;
        // After an application restart, verified output is reusable but the old listener is not.
        // A new upload is prepared only through StartColab with explicit user consent.
        if (key.Length == 0 || data == null) return null;
        string fingerprint = SettingsContract.Fingerprint(settings);
        foreach (int repetitions in new[] { selectedCalibrationRepetitions, lastCalibrationRepetitions }.Distinct())
            if (repetitions >= 100 && key == CalibrationKey(repetitions) && Sessions.HasCalibration(key, datasetHash, fingerprint, repetitions))
                return new ColabRunPlan(key, "standard", "analyze", datasetHash, fingerprint, repetitions, Array.Empty<string>());
        return null;
    }
    private void RefreshColabPanel()
    {
        ColabPanelView? view = colabPanel;
        if (layoutTestMode || view == null || view.State.IsDisposed) return;
        try
        {
            ColabSession? session = view.Key.Length == 0 ? null : Sessions.Find(view.Key);
            ColabRunPlan? plan = ReadOnlyColabPlan(view.Key);
            bool live = Sessions.Live(session, DateTime.UtcNow), busy = Sessions.Busy(session, DateTime.UtcNow);
            bool pending = Sessions.Pending(session, DateTime.UtcNow), connected = live && session!.ControlsReady;
            bool saved = plan != null && Sessions.HasCalibration(plan.Key, plan.DatasetHash, plan.SettingsHash, plan.Repetitions);
            bool standard = plan == null || plan.Kind == "standard";
            view.State.Text = pending && !busy ? T("Command queued / first cell required", "Команда ожидает / нужна первая ячейка")
                : live ? ColabPhaseLabel(session!.Phase) : session == null ? T("Not connected", "Не подключено") : T("Connection not confirmed", "Связь не подтверждена");
            view.Runtime.Text = (session?.RuntimeLabel.Length > 0 ? session.RuntimeLabel : T("Runtime not confirmed", "Среда не подтверждена")) +
                (plan == null ? "" : $"   ·   {plan.Kind}   ·   {plan.Repetitions:N0} " + T("repetitions", "повторов") + $"   ·   {plan.DatasetHash[..Math.Min(10, plan.DatasetHash.Length)]}");
            view.Detail.Text = !live && session != null && !pending
                ? T("The notebook may be closed or unreachable. Its process may still be running. Reopen the same notebook or reconnect. Saved calibration is retained.", "Блокнот может быть закрыт или недоступен. Его процесс может продолжать работать. Откройте тот же блокнот или переподключитесь. Сохранённая калибровка не удаляется.")
                : session?.ProgressMessage.Length > 0 ? session.ProgressMessage
                : pending ? T("Open Connection code if the clipboard changed. Run the updated first cell, paste the code and leave it running.", "Если буфер обмена изменился, откройте «Код подключения». Запустите обновлённую первую ячейку, вставьте код и оставьте её работать.")
                : saved ? T("Verified calibration is available. Analysis will not repeat it.", "Есть проверенная калибровка. Анализ не будет запускать её повторно.")
                : T("Load data and press Calibrate. The app asks permission before transferring a new job.", "Загрузите данные и нажмите «Калибровать». Перед передачей нового задания приложение запросит разрешение.");
            if (live && session!.Percent is int percent)
            {
                view.Progress.Style = ProgressBarStyle.Continuous; view.Progress.Value = busy ? Math.Min(99, percent) : percent;
                view.State.Text += $" · {view.Progress.Value}%";
            }
            else { view.Progress.Style = live && busy ? ProgressBarStyle.Marquee : ProgressBarStyle.Continuous; view.Progress.Value = 0; }
            view.Calibrate.Enabled = !busy && !pending && standard && data != null && !saved;
            view.Analyze.Enabled = !busy && !pending && (standard ? data != null && (saved || calibration != null) : plan != null);
            view.Download.Enabled = !busy && !pending && (saved || connected && session!.Phase is "complete" or "failed");
            view.Stop.Enabled = connected && (busy || pending) && !(pending && session!.RequestedAction == "cancel");
            view.Code.Enabled = ConnectionCode(view.Key).Length > 0;
            view.Reconnect.Enabled = colabPlans.ContainsKey(view.Key);
            view.Disconnect.Enabled = session != null && session.Phase != "disconnected";
        }
        catch (Exception error) { view.Detail.Text = error.Message; }
    }
    private void RunColabPanelAction(string action)
    {
        if (layoutTestMode) return;
        string key = colabPanelKey;
        ColabRunPlan? plan = ReadOnlyColabPlan(key);
        ColabSession? session = key.Length > 0 ? Sessions.Find(key) : null;
        if (action == "download" && !Sessions.Live(session, DateTime.UtcNow)) { SaveReceivedColabResults(key); return; }
        if (plan?.Kind == "standard" && (data == null || plan.DatasetHash != datasetHash || plan.SettingsHash != SettingsContract.Fingerprint(settings)))
        {
            ColabWarning(T("The panel refers to another prepared dataset/settings snapshot. Load that data again, or use Current data to prepare a new job.", "Панель относится к другому подготовленному набору данных/настройкам. Загрузите их снова или нажмите «Задание из текущих данных».")); return;
        }
        if (Sessions.Live(session, DateTime.UtcNow) && session!.ControlsReady && plan != null)
        {
            lock (colabGate) Sessions.QueueAction(key, action);
            RefreshColabPanel(); return;
        }
        if (action is "cancel" or "download") { ColabWarning(T("Reconnect first, or use the notebook's manual result cell.", "Сначала переподключитесь или используйте ячейку скачивания в блокноте.")); return; }
        if (colabPlans.ContainsKey(key)) { ReconnectColab(key); return; }
        StartColab(action, lastCalibrationRepetitions > 0 && action == "analyze" ? lastCalibrationRepetitions : selectedCalibrationRepetitions);
    }
    private string ConnectionCode(string key)
    {
        if (layoutTestMode || colabBridge == null || key.Length == 0 || !colabPlans.ContainsKey(key)) return "";
        ColabSession? session = Sessions.Find(key);
        return session == null || session.Phase == "disconnected" ? "" : $"http://127.0.0.1:{colabBridge.Port}/v1/{session.Token}";
    }
    private bool TryCopyColabCode(string key)
    {
        string code = ConnectionCode(key);
        if (code.Length == 0) return false;
        try { Clipboard.SetText(code); return true; }
        catch (System.Runtime.InteropServices.ExternalException) { return false; }
    }
    private void ShowColabConnection(string key)
    {
        string code = ConnectionCode(key);
        if (code.Length == 0) { ColabWarning(T("Prepare or reconnect a job to get a current code.", "Подготовьте или переподключите задание, чтобы получить действующий код.")); return; }
        using var dialog = new Form { Text = T("Colab connection", "Подключение Colab"), StartPosition = FormStartPosition.CenterParent,
            ClientSize = new Size(800, 650), MinimumSize = new Size(640, 560), AutoScaleMode = AutoScaleMode.Dpi,
            Font = Font, BackColor = Surface, ForeColor = TextColor, MinimizeBox = false, MaximizeBox = false };
        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, Padding = new Padding(24), AutoScroll = true };
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100)); dialog.Controls.Add(layout);
        void Add(Control control) { int row = layout.RowCount++; layout.RowStyles.Add(new RowStyle(SizeType.AutoSize)); control.Dock = DockStyle.Top; control.Margin = new Padding(0, 0, 0, 14); layout.Controls.Add(control, 0, row); }
        Label TextLine(string text) => new() { Text = text, AutoSize = true, MaximumSize = new Size(735, 0), ForeColor = TextColor };
        Add(new Label { Text = T("Your connection code is always here", "Код подключения всегда доступен здесь"), Font = new Font(Font.FontFamily, 16, FontStyle.Bold), AutoSize = true });
        Add(TextLine(T("Run the updated first cell. Paste this code at the hidden prompt and leave the cell running. If an old connection is remembered, enable RESET_CONNECTION before rerunning it.",
            "Запустите обновлённую первую ячейку. Вставьте код в скрытое поле ввода и оставьте ячейку работающей. Если запомнилось старое подключение, перед повторным запуском включите RESET_CONNECTION.")));
        var box = new TextBox { Text = code, ReadOnly = true, UseSystemPasswordChar = true, AccessibleName = T("Private connection code", "Приватный код подключения") };
        Add(box);
        var reveal = new CheckBox { Text = T("Show code", "Показать код"), AutoSize = true };
        reveal.CheckedChanged += (_, _) => box.UseSystemPasswordChar = !reveal.Checked; Add(reveal);
        var feedback = TextLine(T("Closing this window does not delete the code. Open it again from the Colab panel.", "Закрытие этого окна не удаляет код. Откройте его снова из панели Colab."));
        Add(ColabActions(ColabPanelButton("Copy code", "Скопировать код", () => {
            feedback.Text = TryCopyColabCode(key) ? T("Copied. Paste into the Colab prompt.", "Скопировано. Вставьте в поле Colab.") : T("Clipboard is busy. Show and copy the code manually.", "Буфер обмена занят. Покажите и скопируйте код вручную.");
        }, true), ColabPanelButton("Open notebook", "Открыть блокнот", () => OpenBrowser(Sessions.NotebookFor(key)))));
        Add(feedback);
        Add(TextLine(T("Notebook address (optional): paste an existing /drive/ notebook to reopen it without creating another copy.", "Адрес блокнота (необязательно): вставьте существующий адрес /drive/, чтобы открывать его без создания новых копий.")));
        var url = new TextBox { Text = Sessions.NotebookFor(key), AccessibleName = T("Notebook address", "Адрес блокнота") }; Add(url);
        Add(ColabActions(ColabPanelButton("Save address", "Сохранить адрес", () => { Sessions.LinkNotebook(key, url.Text.Trim()); feedback.Text = T("Notebook address saved.", "Адрес блокнота сохранён."); }),
            ColabPanelButton("Save job ZIP…", "Сохранить ZIP задания…", () => SaveColabJob(key))));
        Add(TextLine(T("Do not publish this code: it grants access to this prepared job through the local bridge. Browser local-network permission may be required. Use manual job upload if blocked.",
            "Не публикуйте код: он даёт доступ к подготовленному заданию через локальное соединение. Браузер может запросить доступ к локальной сети. Если доступ запрещён, загрузите ZIP задания вручную.")));
        var close = ColabPanelButton("Close", "Закрыть", dialog.Close); Add(close); dialog.CancelButton = close;
        layout.SizeChanged += (_, _) => { foreach (Label label in layout.Controls.OfType<Label>()) label.MaximumSize = new Size(Math.Max(250, layout.ClientSize.Width - 64), 0); };
        ApplyThemeRecursive(dialog); dialog.ShowDialog(this);
    }
    private void ReconnectColab(string key)
    {
        if (!colabPlans.TryGetValue(key, out var plan)) { ColabWarning(T("Prepare a job from the current data first.", "Сначала подготовьте задание из текущих данных.")); return; }
        if (MessageBox.Show(this, T("Reconnect the same notebook with a new code? The old connection will be revoked; calibration and received results are kept. A cloud calculation may still be running — stop it in Colab first. Reconnection only prepares the controller; it does not repeat calibration.",
            "Переподключить тот же блокнот с новым кодом? Старый код будет отозван; калибровка и полученные результаты сохранятся. Облачный расчёт может ещё работать — сначала остановите его в Colab. Переподключение только подготовит контроллер, не запуская калибровку повторно."),
            "MVS · Colab", MessageBoxButtons.YesNo, MessageBoxIcon.Warning) != DialogResult.Yes) return;
        string url;
        lock (colabGate)
        {
            RefreshColabArchiveCalibration(plan);
            colabBridge ??= new ColabBridge(HandleColabRequest);
            url = Sessions.Launch(key, "prepare");
        }
        TryCopyColabCode(key); RefreshColabPanel(); OpenBrowser(url); ShowColabConnection(key);
    }
    private void DisconnectColab(string key)
    {
        if (MessageBox.Show(this, T("Revoke this connection? This does not stop Google's runtime. Use Stop first if connected. Saved files will not be deleted.",
            "Отозвать подключение? Это не останавливает среду Google. Если связь есть, сначала нажмите «Остановить». Сохранённые файлы не удаляются."),
            "MVS · Colab", MessageBoxButtons.YesNo, MessageBoxIcon.Warning) != DialogResult.Yes) return;
        lock (colabGate) Sessions.Disconnect(key);
        RefreshColabPanel(); RefreshColabButtons();
    }
    private void SelectColabRuntime(string key)
    {
        if (MessageBox.Show(this, T("In Colab choose Runtime → Change runtime type → Python 3 → CPU (recommended). This .NET engine does not use GPU/TPU. Availability and quotas are controlled by Google. Changing the runtime may discard unsaved cloud files: download results first, then reconnect. Open the notebook?",
            "В Colab выберите «Среда выполнения» → «Сменить среду выполнения» → Python 3 → CPU (рекомендуется). Движок .NET не использует GPU/TPU. Доступность и квоты определяет Google. При смене среды несохранённые облачные файлы могут исчезнуть: сначала скачайте результаты, затем переподключитесь. Открыть блокнот?"),
            T("Select runtime", "Выбор среды выполнения"), MessageBoxButtons.OKCancel, MessageBoxIcon.Information) == DialogResult.OK)
            OpenBrowser(Sessions.NotebookFor(key.Length == 0 ? null : key));
    }
    private void SaveColabJob(string key)
    {
        if (!colabPlans.TryGetValue(key, out var plan)) { ColabWarning(T("Prepare a job first.", "Сначала подготовьте задание.")); return; }
        using var save = new SaveFileDialog { Filter = "MVS job ZIP (*.zip)|*.zip", FileName = "MVS_job.zip" };
        if (save.ShowDialog(this) != DialogResult.OK) return;
        lock (colabGate) { RefreshColabArchiveCalibration(plan); File.Copy(Sessions.ArchivePath(key), save.FileName, true); }
    }
    private void SaveShippedColabNotebook()
    {
        byte[] bytes = Branding.ResourceBytes("MVS_Colab.ipynb") ?? throw new InvalidDataException(T("Embedded notebook is missing. Use notebooks/MVS_Colab.ipynb from this release.", "Встроенный блокнот отсутствует. Используйте notebooks/MVS_Colab.ipynb из этого релиза."));
        using var save = new SaveFileDialog { Filter = "Colab notebook (*.ipynb)|*.ipynb", FileName = "MVS_Colab.ipynb" };
        if (save.ShowDialog(this) != DialogResult.OK) return;
        File.WriteAllBytes(save.FileName, bytes);
        MessageBox.Show(this, T("Open this notebook through File → Open notebook → Upload in Colab. Update an old saved notebook once before using the new control panel. After that, reuse it.",
            "Откройте файл в Colab через «Файл» → «Открыть блокнот» → «Загрузка». Перед использованием новой панели один раз обновите старый сохранённый блокнот. Затем используйте его повторно."), "MVS · Colab");
    }
    private void SaveReceivedColabResults(string key)
    {
        ColabRunPlan? plan = ReadOnlyColabPlan(key);
        if (plan == null || !Sessions.HasCalibration(key, plan.DatasetHash, plan.SettingsHash, plan.Repetitions))
            throw new InvalidDataException(T("No verified received results. Download from the notebook or import its result ZIP.", "Нет проверенных полученных результатов. Скачайте их из блокнота или импортируйте ZIP результатов."));
        using var save = new SaveFileDialog { Filter = "MVS results ZIP (*.zip)|*.zip", FileName = "MVS_received_results.zip" };
        if (save.ShowDialog(this) != DialogResult.OK) return;
        string directory = Sessions.DirectoryFor(key), temporary = save.FileName + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            lock (colabGate)
            using (var zip = ZipFile.Open(temporary, ZipArchiveMode.Create))
            {
                zip.CreateEntryFromFile(Sessions.CalibrationPath(key), "calibration/calibration_state.json");
                string result = Path.Combine(directory, "results.json"), manifest = Path.Combine(directory, "run_manifest.json");
                if (File.Exists(result) && File.Exists(manifest))
                {
                    ValidateColabResults(File.ReadAllBytes(result), File.ReadAllBytes(manifest), plan);
                    zip.CreateEntryFromFile(result, "analysis/results.json"); zip.CreateEntryFromFile(manifest, "analysis/run_manifest.json");
                }
                using var writer = new StreamWriter(zip.CreateEntry("README.txt").Open());
                writer.Write("Received MVS files only. This is NOT the full cloud archive. Input data and connection tokens are excluded. Other files listed in the original manifest may remain in Colab.\n");
            }
            File.Move(temporary, save.FileName, true);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
        MessageBox.Show(this, T("Saved the verified files already received by MVS. For all CSV tables and reports, reconnect and download the full archive from Colab.",
            "Сохранены проверенные файлы, уже полученные MVS. Для всех CSV-таблиц и отчётов переподключитесь и скачайте полный архив из Colab."), "MVS · Colab");
    }
    private void ColabWarning(string message) => MessageBox.Show(this, message, "MVS · Colab", MessageBoxButtons.OK, MessageBoxIcon.Warning);
}
