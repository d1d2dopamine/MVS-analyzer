using System.IO.Compression;

namespace MvsAnalyzer;

internal sealed partial class MainForm
{
    private sealed record ColabPanelView(string Key, Label State, Label Detail, Label Runtime, ProgressBar Progress,
        Button Calibrate, Button Analyze, Button Download, Button Stop, Button Code, Button Connect);
    private ColabPanelView? colabPanel;
    private ColabControlForm? colabWindow;
    private string colabWindowAppearance = "";

    private void ShowColabPanel(string? key = null)
    {
        if (key != null) colabPanelKey = key;
        else if (!layoutTestMode && colabPanelKey.Length == 0) colabPanelKey = Sessions.Latest()?.Key ?? "";
        if (colabWindow == null || colabWindow.IsDisposed)
        {
            var window = new ColabControlForm(Font);
            colabWindow = window;
            var timer = new System.Windows.Forms.Timer { Interval = 1000 };
            timer.Tick += (_, _) => RefreshColabPanel();
            window.FormClosed += (_, _) =>
            {
                timer.Stop(); timer.Dispose();
                if (ReferenceEquals(colabWindow, window)) { colabWindow = null; colabPanel = null; }
            };
            BuildColabWindowContent();
            window.Show(this);
            if (!layoutTestMode) timer.Start();
        }
        else
        {
            if (colabPanel?.Key != colabPanelKey) BuildColabWindowContent();
            if (colabWindow.WindowState == FormWindowState.Minimized) colabWindow.WindowState = FormWindowState.Normal;
            colabWindow.Show(); colabWindow.BringToFront(); colabWindow.Activate();
        }
        RefreshColabPanel();
    }

    private Panel ColabActions(params Button[] buttons) => new ActionButtonPanel(true, 2, buttons);

    private Button ColabPanelButton(string en, string ru, Action action, bool primary = false, int width = 205)
    {
        var button = Button(T(en, ru), primary, width);
        button.Height = 44; button.AccessibleName = button.Text;
        button.Click += (_, _) => { try { action(); } catch (Exception error) { ColabWarning(error.Message); } };
        return button;
    }

    private void UpdateColabWindowTheme()
    {
        if (colabWindow == null || colabWindow.IsDisposed) return;
        if (colabWindowAppearance != settings.Language + ":" + Dark) BuildColabWindowContent();
        colabWindow.BackColor = Bg; colabWindow.ForeColor = TextColor;
        ApplyThemeRecursive(colabWindow); colabWindow.Invalidate(true);
    }

    private void BuildColabWindowContent()
    {
        if (colabWindow == null || colabWindow.IsDisposed) return;
        string key = colabPanelKey;
        var page = colabWindow.Content;
        colabPanel = null;
        page.SuspendLayout();
        try
        {
            foreach (Control old in page.Controls.Cast<Control>().ToArray()) old.Dispose();
            page.Controls.Clear();
            colabWindow.BackColor = Bg; colabWindow.ForeColor = TextColor; page.BackColor = Bg;
            colabWindowAppearance = settings.Language + ":" + Dark;
            var runtime = new Label { Text = T("Runtime has not reported yet.", "Среда выполнения ещё не подключена."), ForeColor = Secondary };
            var detail = new Label { Text = T("Load data, connect the notebook once, then use the buttons here.", "Загрузите данные, один раз подключите ноутбук и управляйте расчётом здесь."), ForeColor = TextColor };
            var progress = new ProgressBar { Height = 18, Minimum = 0, Maximum = 100, AccessibleName = T("Colab progress", "Прогресс Colab") };
            var calibrate = ColabPanelButton("Calibrate", "Калибровать", () => RunColabPanelAction("calibrate"), true);
            var analyze = ColabPanelButton("Analyze", "Анализировать", () => RunColabPanelAction("analyze"), true);
            var download = ColabPanelButton("Download results", "Скачать результаты", () => RunColabPanelAction("download"));
            var stop = ColabPanelButton("Stop", "Остановить", () => RunColabPanelAction("cancel"));
            var status = FlowCard(T("Not connected", "Не подключено"), "", runtime, progress, detail,
                ColabActions(calibrate, analyze, download, stop));
            var state = (Label)status.Controls[0];
            status.Margin = new Padding(0, 0, 0, 12); page.Controls.Add(status);
            var connect = ColabPanelButton("Connect…", "Подключить…", () => ConnectColab(key));
            var code = ColabPanelButton("Connection code…", "Код подключения…", () => ShowColabConnection(key));
            var runtimeButton = ColabPanelButton("Runtime…", "Среда выполнения…", () => SelectColabRuntime(key));
            var more = Button(T("More…", "Ещё…"), false, 205); more.AccessibleName = more.Text;
            var menu = new ContextMenuStrip { BackColor = Surface, ForeColor = TextColor, Font = Font, ShowImageMargin = false,
                Renderer = new ThemedMenuRenderer(Surface, TextColor, Secondary, Border, AccentLight) };
            ToolStripMenuItem Item(string en, string ru, Action action)
            {
                var item = new ToolStripMenuItem(T(en, ru)) { BackColor = Surface, ForeColor = TextColor };
                item.Click += (_, _) => { try { action(); } catch (Exception error) { ColabWarning(error.Message); } };
                menu.Items.Add(item); return item;
            }
            Item("Open notebook", "Открыть ноутбук", () => OpenBrowser(Sessions.NotebookFor(key.Length == 0 ? null : key)));
            var prepare = Item("Prepare current data…", "Задание из текущих данных…", () => StartColab("prepare", selectedCalibrationRepetitions));
            var received = Item("Show received results in MVS", "Показать полученные результаты в MVS", () => ShowReceivedColabResults(key));
            menu.Items.Add(new ToolStripSeparator());
            var export = Item("Save job ZIP…", "Сохранить ZIP задания…", () => SaveColabJob(key));
            var local = Item("Save received files…", "Сохранить полученные файлы…", () => SaveReceivedColabResults(key));
            Item("Import result ZIP…", "Импортировать ZIP результатов…", ImportColabBundle);
            Item("Save matching notebook…", "Сохранить ноутбук этой версии…", SaveShippedColabNotebook);
            menu.Items.Add(new ToolStripSeparator());
            var reconnect = Item("Reconnect with a new code…", "Переподключить с новым кодом…", () => ReconnectColab(key));
            var disconnect = Item("Disconnect…", "Отключить связь…", () => DisconnectColab(key));
            menu.Opening += (_, _) =>
            {
                if (layoutTestMode) return;
                var session = key.Length == 0 ? null : Sessions.Find(key);
                var plan = ReadOnlyColabPlan(key);
                bool saved = plan != null && Sessions.HasCalibration(key, plan.DatasetHash, plan.SettingsHash, plan.Repetitions);
                bool busy = Sessions.Busy(session, DateTime.UtcNow) || Sessions.Pending(session, DateTime.UtcNow);
                prepare.Enabled = data != null && !localOperationInProgress && !busy;
                received.Enabled = local.Enabled = saved && !localOperationInProgress;
                export.Enabled = colabPlans.ContainsKey(key);
                reconnect.Enabled = colabPlans.ContainsKey(key) && !busy && !localOperationInProgress;
                disconnect.Enabled = session != null && session.Phase != "disconnected";
            };
            more.Click += (_, _) => menu.Show(more, new Point(0, more.Height));
            more.Disposed += (_, _) => menu.Dispose();
            var connection = FlowCard(T("Connection", "Подключение"), "", ColabActions(connect, code, runtimeButton, more));
            connection.Margin = new Padding(0, 0, 0, 12); page.Controls.Add(connection);
            page.Controls.Add(new Label { Text = T("Closing this window does not stop the cloud job. Accelerator selection is confirmed in Colab.",
                "Закрытие окна не останавливает облачный расчёт. Выбор ускорителя подтверждается в Colab."), ForeColor = Secondary, Margin = Padding.Empty });
            colabPanel = new(key, state, detail, runtime, progress, calibrate, analyze, download, stop, code, connect);
            calibrate.Enabled = analyze.Enabled = download.Enabled = stop.Enabled = code.Enabled = false;
            connect.Enabled = layoutTestMode || data != null || colabPlans.ContainsKey(key);
            ApplyThemeRecursive(colabWindow);
        }
        finally { page.ResumeLayout(true); colabWindow.FitCards(); }
        if (!layoutTestMode) RefreshColabPanel();
    }

    private void ConnectColab(string key)
    {
        if (layoutTestMode || localOperationInProgress) return;
        var session = key.Length == 0 ? null : Sessions.Find(key);
        if (Sessions.Live(session, DateTime.UtcNow) || Sessions.Pending(session, DateTime.UtcNow)) ShowColabConnection(key);
        else if (colabPlans.ContainsKey(key)) ReconnectColab(key);
        else StartColab("prepare", selectedCalibrationRepetitions);
    }

    private void ShowReceivedColabResults(string key)
    {
        var plan = ReadOnlyColabPlan(key);
        if (plan == null || plan.Kind != "standard" || data == null || plan.DatasetHash != datasetHash || plan.SettingsHash != SettingsContract.Fingerprint(settings))
        { ColabWarning(T("Load this job's data and settings first.", "Сначала загрузите данные и настройки этого задания.")); return; }
        ReceiveColabState(plan); Navigate(results == null ? "calibration" : "results");
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
            bool matches = !standard || plan != null && data != null && plan.DatasetHash == datasetHash &&
                plan.SettingsHash == SettingsContract.Fingerprint(settings) &&
                (loadedProcessing == null || loadedProcessing == ProcessingSnapshot.From(settings));
            view.State.Text = pending && !busy ? T("Waiting for the notebook", "Ожидание ноутбука")
                : live ? ColabPhaseLabel(session!.Phase) : session == null ? T("Not connected", "Не подключено") : T("Connection not confirmed", "Связь не подтверждена");
            view.State.ForeColor = live && session!.Phase == "failed"
                ? (Dark ? Color.FromArgb(244, 163, 163) : Color.FromArgb(176, 40, 40)) : TextColor;
            view.Runtime.Text = session?.RuntimeLabel.Length > 0 ? session.RuntimeLabel
                : T("Runtime not confirmed · CPU is sufficient for MVS", "Среда не подтверждена · для MVS достаточно CPU");
            view.Detail.Text = localOperationInProgress
                ? T("A local calculation is running. Remote files are retained separately until it finishes.", "Выполняется локальный расчёт. Облачные файлы сохраняются отдельно и не меняют его данные.")
                : connected && !matches && standard
                ? T("This window controls a different data/settings snapshot. Stop and Download still work. To compute with the current data, use More → Prepare current data.", "Это задание относится к другим данным или настройкам. Остановка и скачивание доступны. Для нового расчёта: «Ещё» → «Задание из текущих данных».")
                : !live && session != null && !pending
                ? T("Open the same notebook and reconnect. Saved files are retained; a cloud process may still be running.", "Откройте тот же ноутбук и переподключитесь. Сохранённые файлы остаются; облачный процесс может ещё работать.")
                : session?.ProgressMessage.Length > 0 ? session.ProgressMessage
                : pending ? T("Open Connection code, run the first cell, paste the code and leave that cell running.", "Откройте «Код подключения», запустите первую ячейку, вставьте код и оставьте её работающей.")
                : saved ? T("Verified calibration is available. Analysis will reuse it.", "Проверенная калибровка сохранена. Анализ использует её без повторного расчёта.")
                : connected ? T("Ready. Calibrate, then analyze. Stop requests cancellation of the current calculation only.", "Готово. Выполните калибровку, затем анализ. «Остановить» отменяет только текущий расчёт.")
                : T("Load data, then click Connect. MVS asks permission before a new transfer.", "Загрузите данные и нажмите «Подключить». Перед передачей MVS запросит разрешение.");
            if (live && session!.Percent is int percent)
            {
                view.Progress.Style = ProgressBarStyle.Continuous; view.Progress.Value = busy ? Math.Min(99, percent) : percent;
                view.State.Text += $" · {view.Progress.Value}%";
            }
            else { view.Progress.Style = live && busy ? ProgressBarStyle.Marquee : ProgressBarStyle.Continuous; view.Progress.Value = 0; }
            bool idle = !localOperationInProgress && !busy && !pending;
            view.Calibrate.Enabled = idle && connected && standard && matches && !saved;
            view.Analyze.Enabled = idle && connected && matches && (standard ? saved : plan != null);
            view.Download.Enabled = idle && (saved || connected && session!.Phase is "complete" or "failed");
            // Stop/download refer to the prepared remote job, not whatever data is now open locally.
            view.Stop.Enabled = !localOperationInProgress && connected && (busy || pending) &&
                session!.Phase != "cancelling" && !(pending && session.RequestedAction == "cancel");
            view.Code.Enabled = ConnectionCode(view.Key).Length > 0;
            view.Connect.Text = connected ? T("Connection settings…", "Параметры связи…")
                : pending ? T("Connection code…", "Код подключения…")
                : colabPlans.ContainsKey(view.Key) ? T("Reconnect…", "Переподключить…") : T("Connect…", "Подключить…");
            view.Connect.Enabled = !localOperationInProgress && (connected || pending || data != null || colabPlans.ContainsKey(view.Key));
        }
        catch (Exception error)
        {
            view.Calibrate.Enabled = view.Analyze.Enabled = false;
            view.Detail.Text = error.Message;
        }
    }

    private void RunColabPanelAction(string action)
    {
        if (layoutTestMode || localOperationInProgress) return;
        string key = colabPanel?.Key ?? colabPanelKey;
        ColabSession? session = key.Length > 0 ? Sessions.Find(key) : null;
        bool live = Sessions.Live(session, DateTime.UtcNow);
        if (action == "download" && !live) { SaveReceivedColabResults(key); return; }
        // A user must be able to stop an OLD job after opening a NEW local dataset.
        if (action is "cancel" or "download")
        {
            if (!live || !session!.ControlsReady) { ColabWarning(T("Reconnect the controller first.", "Сначала переподключите контроллер.")); return; }
            lock (colabGate) Sessions.QueueAction(key, action);
            RefreshColabPanel(); return;
        }
        ColabRunPlan? plan = ReadOnlyColabPlan(key);
        if (plan == null || !live || !session!.ControlsReady)
        { ConnectColab(key); return; }
        if (plan.Kind == "standard" && (data == null || plan.DatasetHash != datasetHash ||
            plan.SettingsHash != SettingsContract.Fingerprint(settings) || loadedProcessing != null && loadedProcessing != ProcessingSnapshot.From(settings)))
        {
            ColabWarning(T("This job belongs to other data/settings. Use More → Prepare current data, or reload that job's data.",
                "Задание относится к другим данным/настройкам. Выберите «Ещё» → «Задание из текущих данных» или загрузите данные этого задания.")); return;
        }
        lock (colabGate) Sessions.QueueAction(key, action);
        RefreshColabPanel();
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
            ClientSize = new Size(640, 600), MinimumSize = new Size(540, 480), AutoScaleMode = AutoScaleMode.Dpi,
            Font = Font, BackColor = Surface, ForeColor = TextColor, MinimizeBox = false, MaximizeBox = false };
        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, Padding = new Padding(24), AutoScroll = true };
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100)); dialog.Controls.Add(layout);
        void Add(Control control) { int row = layout.RowCount++; layout.RowStyles.Add(new RowStyle(SizeType.AutoSize)); control.Dock = DockStyle.Top; control.Margin = new Padding(0, 0, 0, 14); layout.Controls.Add(control, 0, row); }
        Label TextLine(string text) => new() { Text = text, AutoSize = true, MaximumSize = new Size(560, 0), ForeColor = TextColor };
        Add(new Label { Text = T("Connect the notebook once", "Подключите ноутбук один раз"), Font = new Font(Font.FontFamily, 16, FontStyle.Bold), AutoSize = true });
        Add(TextLine(T("Run the updated first cell. Paste this code at the hidden prompt and leave the cell running. If an old connection is remembered, enable RESET_CONNECTION before rerunning it.",
            "Запустите обновлённую первую ячейку. Вставьте код в скрытое поле ввода и оставьте ячейку работающей. Если запомнилось старое подключение, перед повторным запуском включите RESET_CONNECTION.")));
        var box = new TextBox { Text = code, ReadOnly = true, UseSystemPasswordChar = true, AccessibleName = T("Private connection code", "Приватный код подключения") };
        Add(box);
        var reveal = new CheckBox { Text = T("Show code", "Показать код"), AutoSize = true };
        reveal.CheckedChanged += (_, _) => box.UseSystemPasswordChar = !reveal.Checked; Add(reveal);
        var feedback = TextLine(T("Closing this window does not delete the code. Open it again from the Colab window.", "Закрытие этого окна не удаляет код. Откройте его снова из окна Colab."));
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
        dialog.BackColor = Surface; ApplyThemeRecursive(dialog); dialog.ShowDialog(ColabDialogOwner);
    }
    private void ReconnectColab(string key)
    {
        if (!colabPlans.TryGetValue(key, out var plan)) { ColabWarning(T("Prepare a job from the current data first.", "Сначала подготовьте задание из текущих данных.")); return; }
        if (MessageBox.Show(ColabDialogOwner, T("Reconnect the same notebook with a new code? The old connection will be revoked; calibration and received results are kept. A cloud calculation may still be running — stop it in Colab first. Reconnection only prepares the controller; it does not repeat calibration.",
            "Переподключить тот же блокнот с новым кодом? Старый код будет отозван; калибровка и полученные результаты сохранятся. Облачный расчёт может ещё работать — сначала остановите его в Colab. Переподключение только подготовит контроллер, не запуская калибровку повторно."),
            "MVS · Colab", MessageBoxButtons.YesNo, MessageBoxIcon.Warning) != DialogResult.Yes) return;
        lock (colabGate)
        {
            RefreshColabArchiveCalibration(plan);
            colabBridge ??= new ColabBridge(HandleColabRequest);
            Sessions.Launch(key, "prepare");
        }
        TryCopyColabCode(key); RefreshColabPanel(); ShowColabConnection(key);
    }
    private void DisconnectColab(string key)
    {
        if (MessageBox.Show(ColabDialogOwner, T("Revoke this connection? This does not stop Google's runtime. Use Stop first if connected. Saved files will not be deleted.",
            "Отозвать подключение? Это не останавливает среду Google. Если связь есть, сначала нажмите «Остановить». Сохранённые файлы не удаляются."),
            "MVS · Colab", MessageBoxButtons.YesNo, MessageBoxIcon.Warning) != DialogResult.Yes) return;
        lock (colabGate) Sessions.Disconnect(key);
        RefreshColabPanel(); RefreshColabButtons();
    }
    private IWin32Window ColabDialogOwner => colabWindow is { IsDisposed: false, Visible: true } ? colabWindow : this;

    private void SelectColabRuntime(string key)
    {
        var session = key.Length == 0 || layoutTestMode ? null : Sessions.Find(key);
        if (!layoutTestMode && (Sessions.Busy(session, DateTime.UtcNow) || Sessions.Pending(session, DateTime.UtcNow)))
        { ColabWarning(T("Stop the current job and save its results before changing the runtime.", "Перед сменой среды остановите задание и сохраните результаты.")); return; }
        // The loopback notebook bridge does not expose Google's account-specific accelerator
        // chooser. Do not invent a GPU list or claim that opening a browser switches hardware.
        using var dialog = new Form { Text = T("Colab runtime", "Среда выполнения Colab"),
            Font = Font, BackColor = Bg, ForeColor = TextColor, AutoScaleMode = AutoScaleMode.Dpi,
            StartPosition = FormStartPosition.CenterParent, ClientSize = new Size(590, 430), MinimumSize = new Size(510, 400),
            MaximizeBox = false, MinimizeBox = false };
        var page = new BufferedFlowPanel { Dock = DockStyle.Fill, AutoScroll = true, FlowDirection = FlowDirection.TopDown,
            WrapContents = false, Padding = new Padding(16), BackColor = Bg };
        dialog.Controls.Add(page);
        var current = new Label { Text = session?.RuntimeLabel.Length > 0 ? session.RuntimeLabel : T("Current hardware is not confirmed.", "Текущее оборудование не подтверждено."), ForeColor = Secondary };
        var explanation = new Label { ForeColor = TextColor, Text = T(
            "1. Save your results before switching: cloud files may be lost.\n2. Open the notebook. Choose Runtime → Change runtime type.\n3. Select an accelerator available to your Google account and confirm.\n4. Reconnect from MVS and rerun the first cell with the new code.\n\nThis MVS .NET engine uses CPU, not GPU/TPU. Selecting a GPU will not accelerate its calculations. Google controls accelerator availability and quotas.",
            "1. Сначала сохраните результаты: при смене среды облачные файлы могут исчезнуть.\n2. Откройте ноутбук: «Среда выполнения» → «Сменить среду выполнения».\n3. Выберите доступный вашему аккаунту ускоритель и подтвердите.\n4. Переподключитесь из MVS и запустите первую ячейку с новым кодом.\n\nДвижок MVS на .NET использует CPU, а не GPU/TPU. Выбор GPU не ускоряет его расчёты. Доступность ускорителей и квоты определяет Google.") };
        var open = ColabPanelButton("Open Colab", "Открыть Colab", () => OpenBrowser(Sessions.NotebookFor(key.Length == 0 ? null : key)), true);
        var close = ColabPanelButton("Close", "Закрыть", dialog.Close);
        var card = FlowCard(T("Hardware accelerator", "Аппаратный ускоритель"), "", current, explanation, ColabActions(open, close));
        page.Controls.Add(card); dialog.CancelButton = close;
        void Fit() { card.Width = Math.Max(200, page.ClientSize.Width - page.Padding.Horizontal - SystemInformation.VerticalScrollBarWidth - 2); }
        page.SizeChanged += (_, _) => Fit(); Fit(); dialog.BackColor = Surface; ApplyThemeRecursive(dialog); dialog.ShowDialog(ColabDialogOwner);
    }
    private void SaveColabJob(string key)
    {
        if (!colabPlans.TryGetValue(key, out var plan)) { ColabWarning(T("Prepare a job first.", "Сначала подготовьте задание.")); return; }
        using var save = new SaveFileDialog { Filter = "MVS job ZIP (*.zip)|*.zip", FileName = "MVS_job.zip" };
        if (save.ShowDialog(ColabDialogOwner) != DialogResult.OK) return;
        lock (colabGate) { RefreshColabArchiveCalibration(plan); File.Copy(Sessions.ArchivePath(key), save.FileName, true); }
    }
    private void SaveShippedColabNotebook()
    {
        byte[] bytes = Branding.ResourceBytes("MVS_Colab.ipynb") ?? throw new InvalidDataException(T("Embedded notebook is missing. Use notebooks/MVS_Colab.ipynb from this release.", "Встроенный блокнот отсутствует. Используйте notebooks/MVS_Colab.ipynb из этого релиза."));
        using var save = new SaveFileDialog { Filter = "Colab notebook (*.ipynb)|*.ipynb", FileName = "MVS_Colab.ipynb" };
        if (save.ShowDialog(ColabDialogOwner) != DialogResult.OK) return;
        File.WriteAllBytes(save.FileName, bytes);
        MessageBox.Show(ColabDialogOwner, T("Open this notebook through File → Open notebook → Upload in Colab. Update an old saved notebook once before using the separate control window. After that, reuse it.",
            "Откройте файл в Colab через «Файл» → «Открыть блокнот» → «Загрузка». Перед использованием отдельного окна управления один раз обновите старый сохранённый блокнот. Затем используйте его повторно."), "MVS · Colab");
    }
    private void SaveReceivedColabResults(string key)
    {
        ColabRunPlan? plan = ReadOnlyColabPlan(key);
        if (plan == null || !Sessions.HasCalibration(key, plan.DatasetHash, plan.SettingsHash, plan.Repetitions))
            throw new InvalidDataException(T("No verified received results. Download from the notebook or import its result ZIP.", "Нет проверенных полученных результатов. Скачайте их из блокнота или импортируйте ZIP результатов."));
        using var save = new SaveFileDialog { Filter = "MVS results ZIP (*.zip)|*.zip", FileName = "MVS_received_results.zip" };
        if (save.ShowDialog(ColabDialogOwner) != DialogResult.OK) return;
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
        MessageBox.Show(ColabDialogOwner, T("Saved the verified files already received by MVS. For all CSV tables and reports, reconnect and download the full archive from Colab.",
            "Сохранены проверенные файлы, уже полученные MVS. Для всех CSV-таблиц и отчётов переподключитесь и скачайте полный архив из Colab."), "MVS · Colab");
    }
    private void ColabWarning(string message) => MessageBox.Show(ColabDialogOwner, message, "MVS · Colab", MessageBoxButtons.OK, MessageBoxIcon.Warning);
}
