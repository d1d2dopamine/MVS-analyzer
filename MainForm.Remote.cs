using System.Diagnostics;
using System.Globalization;

namespace MvsAnalyzer;

/// <summary>
/// The remote run section of Settings. Like the benchmark card it lives in its own partial file, so
/// the rest of the window pays one line for it.
///
/// Why this exists: a calibration is thousands of simulations, and the honest profiles of the
/// benchmark take hours. On a laptop that means choosing between the analysis and using the
/// computer. Handing the same work to a hosted notebook removes that choice for people who have no
/// cluster, which is most people this program is for.
///
/// What it deliberately does not do: replace the local run. Everything here is additive. The window
/// still performs the whole analysis offline, and for measurements that must not leave a building
/// that is the only correct way to use it.
/// </summary>
internal sealed partial class MainForm
{
    private string lastJobArchive = "";

    private void AddRemoteCard(FlowLayoutPanel page)
    {
        var card = Card(
            T("Remote run", "Удалённый запуск"),
            T("Opens a notebook that runs the same calibration, analysis and benchmark on borrowed hardware, in three cells: calibrate, analyse, download the results. The local run stays exactly as it is; this is an extra route for work that does not fit on this machine.",
              "Открывает ноутбук, который выполняет ту же калибровку, анализ и бенчмарк на чужих мощностях, в три ячейки: калибровка, анализ, скачивание результатов. Локальный запуск остаётся прежним — это дополнительный путь для работы, которая не умещается на этом компьютере."),
            440);

        var status = new Label
        {
            Text = T("Nothing has been sent anywhere.", "Ничего никуда не отправлено."),
            AutoSize = true,
            MaximumSize = new Size(760, 0),
            ForeColor = Secondary,
            Location = new Point(20, 330)
        };

        var colab = Button(T("Colab: calibration and analysis", "Colab: калибровка и анализ"), true, 330);
        colab.Location = new Point(20, 100);
        colab.Click += (_, _) => Open(RemoteJob.ColabUrl("analysis"), status,
            T("Colab opened. Run the cells from top to bottom.", "Colab открыт. Запускайте ячейки сверху вниз."));
        card.Controls.Add(colab);

        var colabBenchmark = Button(T("Colab: benchmark", "Colab: бенчмарк"), false, 300);
        colabBenchmark.Location = new Point(364, 100);
        colabBenchmark.Click += (_, _) => Open(RemoteJob.ColabUrl("benchmark"), status,
            T("Colab opened. The benchmark invents its own data, so nothing of yours is uploaded.",
              "Colab открыт. Бенчмарк сам создаёт данные, ваши файлы никуда не отправляются."));
        card.Controls.Add(colabBenchmark);

        var bundle = Button(T("Build a job archive", "Собрать задание"), false, 260);
        bundle.Location = new Point(20, 154);
        bundle.Click += (_, _) => BuildJob(status);
        card.Controls.Add(bundle);

        var kaggle = Button(T("Kaggle", "Kaggle"), false, 160);
        kaggle.Location = new Point(292, 154);
        kaggle.Click += (_, _) => Open(RemoteJob.KaggleUrl(), status,
            T("Kaggle opened. Import the notebook from the repository, then enable internet in the session settings.",
              "Kaggle открыт. Импортируйте ноутбук из репозитория и включите интернет в настройках сессии."));
        card.Controls.Add(kaggle);

        var repository = Button(T("Repository", "Репозиторий"), false, 200);
        repository.Location = new Point(464, 154);
        repository.Click += (_, _) => Open(RemoteJob.RepositoryUrl(), status, "");
        card.Controls.Add(repository);

        card.Controls.Add(new Label
        {
            Text = T("A job archive carries the data together with every setting, so the remote run is the same analysis rather than a similar one. Upload it in the first cell; the notebook reads the settings from it instead of asking.",
                     "Задание содержит данные вместе со всеми настройками, поэтому удалённый запуск — тот же анализ, а не похожий. Загрузите его в первую ячейку: ноутбук возьмёт настройки оттуда и не будет спрашивать."),
            AutoSize = true,
            MaximumSize = new Size(760, 0),
            ForeColor = Secondary,
            Location = new Point(20, 210)
        });

        card.Controls.Add(new Label
        {
            Text = T("Measurements uploaded to a hosted notebook leave this computer. For identifiable or restricted data, run the analysis here instead. The benchmark is different: it generates everything from a seed, so it can be run remotely with nothing at stake.",
                     "Данные, загруженные в чужой ноутбук, покидают этот компьютер. Для персональных или закрытых данных запускайте анализ здесь. С бенчмарком иначе: он полностью создаёт данные из зерна, поэтому его можно считать удалённо без риска."),
            AutoSize = true,
            MaximumSize = new Size(760, 0),
            ForeColor = Color.FromArgb(176, 66, 27),
            Location = new Point(20, 262)
        });

        card.Controls.Add(status);
        card.Controls.Add(new Label
        {
            Text = "github.com/" + RemoteJob.Repository + "   ·   " + RemoteJob.NotebookPath("analysis"),
            AutoSize = true,
            ForeColor = Secondary,
            Location = new Point(20, 400)
        });

        page.Controls.Add(card);
    }

    private void Open(string url, Label status, string message)
    {
        try
        {
            Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
            if (message.Length > 0) status.Text = message;
        }
        catch (Exception error)
        {
            status.Text = T("The browser could not be opened: ", "Не удалось открыть браузер: ") + error.Message +
                Environment.NewLine + url;
        }
    }

    /// <summary>
    /// Packs a dataset and the current settings into one archive. The file is picked here rather
    /// than taken from whatever happens to be loaded, so a job can be prepared for data that is not
    /// the data on screen.
    /// </summary>
    private void BuildJob(Label status)
    {
        try
        {
            using var dialog = new OpenFileDialog
            {
                Title = T("Choose the measurements", "Выберите файл измерений"),
                Filter = T("Measurements (*.csv)|*.csv|All files (*.*)|*.*",
                           "Измерения (*.csv)|*.csv|Все файлы (*.*)|*.*"),
            };
            if (dialog.ShowDialog(this) != DialogResult.OK) return;

            string folder = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "MVS_jobs");
            string archive = RemoteJob.WriteBundle(
                folder,
                dialog.FileName,
                OutputExporter.HashFile(dialog.FileName),
                T("Remote job", "Удалённое задание"),
                "",
                settings,
                settings.CustomRepetitions);

            lastJobArchive = archive;
            status.Text = T("Job built: ", "Задание собрано: ") + Path.GetFileName(archive) +
                Environment.NewLine +
                T("Upload this file in the first cell of the notebook.",
                  "Загрузите этот файл в первую ячейку ноутбука.");
            OpenFolder(folder);
        }
        catch (Exception error)
        {
            status.Text = T("The job could not be built: ", "Не удалось собрать задание: ") + error.Message;
        }
    }
}
