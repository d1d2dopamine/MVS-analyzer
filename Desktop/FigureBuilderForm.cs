using System.Text.Json;

namespace MvsAnalyzer;

internal sealed class FigureBuilderForm : Form
{
    private readonly TextBox name = new() { Width = 320 };
    private readonly ThemedComboBox source = new() { Width = 220 };
    private readonly ThemedComboBox chart = new() { Width = 220 };
    private readonly ThemedComboBox xAxis = new() { Width = 220 };
    private readonly ThemedComboBox yAxis = new() { Width = 220 };
    private readonly ThemedComboBox grouping = new() { Width = 220 };
    private readonly TextBox description = new() { Width = 500, Height = 54, Multiline = true };
    private readonly bool dark;
    private readonly Color surface;
    private readonly Color text;
    private readonly Color accent;
    public string? SavedFile { get; private set; }

    public FigureBuilderForm(bool darkMode, Color surfaceColor, Color textColor, Color accentColor, bool russian)
    {
        dark = darkMode; surface = surfaceColor; text = textColor; accent = accentColor;
        Text = russian ? "Конструктор графика" : "Custom figure builder"; ClientSize = new Size(720, 570); StartPosition = FormStartPosition.CenterParent; Font = new Font("Segoe UI", 10); AutoScaleMode = AutoScaleMode.Dpi; BackColor = dark ? Color.FromArgb(31,31,31) : Color.FromArgb(246,247,249); ForeColor = text;
        source.Items.AddRange(new object[] { "results", "calibration", "participants", "trials" }); chart.Items.AddRange(new object[] { "bar", "scatter", "histogram", "line", "box" }); xAxis.Items.AddRange(new object[] { "metric", "group", "trial", "rt" }); yAxis.Items.AddRange(new object[] { "mvs_score", "power", "fpr", "median_rt", "rt" }); grouping.Items.AddRange(new object[] { "none", "group", "metric", "session" });
        foreach (var c in new[] { source, chart, xAxis, yAxis, grouping }) { c.SelectedIndex = 0; c.ApplyTheme(dark, surface, text, accent); }
        int y=24; AddField(russian?"Название":"Name", name, ref y); AddField(russian?"Источник":"Source", source, ref y); AddField(russian?"Тип":"Chart type", chart, ref y); AddField("X", xAxis, ref y); AddField("Y", yAxis, ref y); AddField(russian?"Группировка":"Grouping", grouping, ref y); AddField(russian?"Описание":"Description", description, ref y, 78);
        var save = new Button { Text = russian ? "Сохранить шаблон" : "Save template", Location = new Point(28, y+8), Size = new Size(180, 40), BackColor = accent, ForeColor = Color.White, FlatStyle = FlatStyle.Flat, UseVisualStyleBackColor = false };
        save.Click += (_,_) => SaveTemplate(russian); Controls.Add(save);
    }
    private void AddField(string label, Control control, ref int y, int height=58)
    {
        Controls.Add(new Label { Text=label, AutoSize=true, Location=new Point(28,y+5) }); control.Location=new Point(190,y); control.BackColor=surface; control.ForeColor=text; Controls.Add(control); y+=height;
    }
    private void SaveTemplate(bool russian)
    {
        if (string.IsNullOrWhiteSpace(name.Text)) { MessageBox.Show(russian?"Введите название.":"Enter a template name."); return; }
        string folder=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"MVS_Analyzer","figure-templates"); Directory.CreateDirectory(folder);
        string id=new string(name.Text.ToLowerInvariant().Select(c=>char.IsLetterOrDigit(c)?c:'_').ToArray()).Trim('_'); if (id.Length==0) id="custom_figure";
        var template=new { id, name=name.Text.Trim(), source=source.Text, chart=chart.Text, x=xAxis.Text, y=yAxis.Text, grouping=grouping.Text, description=description.Text.Trim(), version=1 };
        SavedFile=Path.Combine(folder,id+".json"); File.WriteAllText(SavedFile,JsonSerializer.Serialize(template,new JsonSerializerOptions{WriteIndented=true})); DialogResult=DialogResult.OK; Close();
    }
}
