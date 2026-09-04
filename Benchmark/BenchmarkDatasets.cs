using System.Globalization;

namespace MvsAnalyzer.Benchmarking;

internal enum InjectionMode
{
    None = 0,
    Location = 1,
    Dispersion = 2
}

internal enum DataShape
{
    Normal = 0,
    HeavyTail = 1,
    Lognormal = 2
}

/// <summary>
/// One synthetic study design. The numbers are chosen to look like the measurement families the
/// program is aimed at, not to flatter any particular metric: a gait-like design with a low
/// within-subject coefficient of variation and many measurements, and a voice-like design with a
/// high coefficient of variation and few measurements.
/// </summary>
internal sealed record BenchmarkDesign(
    string Id,
    string Label,
    string LabelRu,
    int EntitiesPerGroup,
    int MeasurementsPerEntity,
    double BaseLevel,
    double BetweenSd,
    double WithinCv,
    double CvHeterogeneity,
    DataShape Shape,
    string Variable,
    string Unit);

internal sealed class RealDataset
{
    public required string Name { get; init; }
    public required string FileHash { get; init; }
    public required List<Observation> Pool { get; init; }
    public required int Entities { get; init; }
    public required int MinMeasurements { get; init; }
}

internal static class BenchmarkDatasets
{
    /// <summary>
    /// Stride-interval-like. Sixteen entities per group and forty measurements each mirrors the size
    /// of the public gait recordings the protocol names as its real-data target.
    /// </summary>
    public static readonly BenchmarkDesign Gait = new(
        "gait_stride_like", "Gait-like: 16 per group, 40 measurements, CV about 2.5%",
        "Как шаг: 16 на группу, 40 измерений, КВ около 2,5%",
        16, 40, 1.10, .08, .025, .25, DataShape.HeavyTail, "stride_interval", "s");

    /// <summary>Voice-jitter-like: noisier, shorter, right-skewed. A deliberately harder design.</summary>
    public static readonly BenchmarkDesign Voice = new(
        "voice_jitter_like", "Voice-like: 20 per group, 26 measurements, CV about 18%",
        "Как голос: 20 на группу, 26 измерений, КВ около 18%",
        20, 26, .0055, .0018, .18, .35, DataShape.Lognormal, "jitter", "");

    public static readonly BenchmarkDesign[] All = { Gait, Voice };

    public static BenchmarkDesign WithShape(BenchmarkDesign design, DataShape shape) => design with { Shape = shape };

    public static string ShapeId(DataShape shape) => shape switch
    {
        DataShape.HeavyTail => "heavy_tail",
        DataShape.Lognormal => "lognormal",
        _ => "normal"
    };

    public static string ModeId(InjectionMode mode) => mode switch
    {
        InjectionMode.Location => "location",
        InjectionMode.Dispersion => "dispersion",
        _ => "none"
    };

    /// <summary>
    /// Builds one synthetic study.
    ///
    /// Two properties matter and both are deliberate. First, the number of random draws does not
    /// depend on the injected effect or on the contamination rate: the contamination draw is always
    /// taken and then used or ignored. That gives common random numbers, so two conditions that
    /// share a seed differ only by the thing under study and the power comparison is not swamped by
    /// Monte Carlo noise. Second, the entity means and the entity spreads are drawn separately, so
    /// a location effect really does leave the spread alone and a dispersion effect really does
    /// leave the level alone.
    /// </summary>
    public static List<Observation> Generate(BenchmarkDesign design, InjectionMode mode, double effect, double contamination, BenchmarkRandom random)
    {
        string[] groups = { "control", "case" };
        var rows = new List<Observation>(groups.Length * design.EntitiesPerGroup * design.MeasurementsPerEntity);
        for (int g = 0; g < groups.Length; g++)
        {
            for (int e = 1; e <= design.EntitiesPerGroup; e++)
            {
                double level = design.BaseLevel + design.BetweenSd * random.NextGaussian();
                if (level < design.BaseLevel * .25) level = design.BaseLevel * .25;
                double cv = design.WithinCv * Math.Exp(design.CvHeterogeneity * random.NextGaussian());
                bool treated = g == 1;
                double shift = treated && mode == InjectionMode.Location ? design.BaseLevel * (effect - 1) : 0;
                if (treated && mode == InjectionMode.Dispersion) cv *= effect;
                string entity = groups[g] + "_" + e.ToString("00", CultureInfo.InvariantCulture);
                for (int s = 1; s <= design.MeasurementsPerEntity; s++)
                {
                    double noise = design.Shape switch
                    {
                        DataShape.HeavyTail => random.NextStandardizedT(5),
                        DataShape.Lognormal => random.NextStandardizedLognormal(.6),
                        _ => random.NextGaussian()
                    };
                    double value = level * (1 + cv * noise);
                    double contaminationDraw = random.NextDouble();
                    double side = random.NextDouble();
                    if (contamination > 0 && contaminationDraw < contamination)
                        value += (side < .5 ? -1 : 1) * 5 * level * cv;
                    double floor = design.BaseLevel * .02;
                    if (value < floor) value = floor;
                    value += shift; // additive AFTER flooring; residual spread is identical under a shared seed
                    rows.Add(new Observation(entity, groups[g], value, s, design.Variable, design.Unit));
                }
            }
        }
        return rows;
    }

    /// <summary>
    /// Plasmode design for real recordings. Real data never comes with a known truth, so the truth
    /// is manufactured instead of assumed: entities from a single real group are shuffled and split
    /// into two pseudo-groups, which defines an exchangeable randomization null, not equality in each realised split, and then
    /// the effect under test is injected into one half. The within-entity noise, the skew and the
    /// tails stay exactly as they were measured in the laboratory.
    /// </summary>
    public static List<Observation> Plasmode(RealDataset dataset, InjectionMode mode, double effect, int entitiesPerGroup, int measurements, BenchmarkRandom random)
    {
        var byEntity = new Dictionary<string, List<double>>(StringComparer.Ordinal);
        var order = new List<string>();
        foreach (Observation row in dataset.Pool)
        {
            if (!byEntity.TryGetValue(row.Entity, out List<double>? values))
            {
                values = new List<double>();
                byEntity[row.Entity] = values;
                order.Add(row.Entity);
            }
            values.Add(row.Value);
        }
        var usable = order.Where(x => byEntity[x].Count >= measurements).ToList();
        if (usable.Count < entitiesPerGroup * 2)
            throw new InvalidDataException("The real dataset does not hold enough entities for a plasmode split.");
        for (int i = usable.Count - 1; i > 0; i--)
        {
            int j = random.Next(i + 1);
            (usable[i], usable[j]) = (usable[j], usable[i]);
        }
        double commonShiftScale = Math.Abs(dataset.Pool.Average(x => x.Value));
        string[] groups = { "control", "case" };
        var rows = new List<Observation>(entitiesPerGroup * 2 * measurements);
        for (int g = 0; g < groups.Length; g++)
        {
            for (int e = 0; e < entitiesPerGroup; e++)
            {
                string source = usable[g * entitiesPerGroup + e];
                List<double> values = byEntity[source];
                int start = values.Count > measurements ? random.Next(values.Count - measurements + 1) : 0;
                var window = new double[measurements];
                for (int s = 0; s < measurements; s++) window[s] = values[start + s];
                double centre = window.Average();
                string entity = groups[g] + "_" + (e + 1).ToString("00", CultureInfo.InvariantCulture);
                bool treated = g == 1;
                for (int s = 0; s < measurements; s++)
                {
                    double value = window[s];
                    if (treated && mode == InjectionMode.Location) value += commonShiftScale * (effect - 1);
                    if (treated && mode == InjectionMode.Dispersion) value = centre + (value - centre) * effect;
                    rows.Add(new Observation(entity, groups[g], value, s + 1, "plasmode_value", ""));
                }
            }
        }
        return rows;
    }

    /// <summary>
    /// Loads any prepared CSV files the operator dropped into a folder. The archive cannot ship the
    /// public recordings themselves, only the converter, so this stays optional: without a folder
    /// the benchmark still produces its full synthetic result.
    /// </summary>
    public static List<RealDataset> LoadReal(string folder, int minMeasurements, List<string> notes)
    {
        var datasets = new List<RealDataset>();
        if (string.IsNullOrWhiteSpace(folder)) return datasets;
        string[] files;
        try
        {
            if (!Directory.Exists(folder))
            {
                notes.Add("Real-data folder not found: " + folder);
                return datasets;
            }
            files = Directory.GetFiles(folder, "*.csv", SearchOption.TopDirectoryOnly).OrderBy(x => x, StringComparer.Ordinal).ToArray();
        }
        catch (Exception ex)
        {
            notes.Add("Real-data folder unreadable: " + ex.Message);
            return datasets;
        }
        foreach (string file in files)
        {
            try
            {
                List<Observation> observations = CsvImporter.Read(file, -1000000, 1000000);
                var byGroup = observations.GroupBy(x => x.Group, StringComparer.Ordinal)
                    .Select(g => new { Group = g.Key, Rows = g.ToList() })
                    .OrderByDescending(x => x.Rows.Select(r => r.Entity).Distinct(StringComparer.Ordinal).Count())
                    .ThenBy(x => x.Group, StringComparer.Ordinal)
                    .ToList();
                if (byGroup.Count == 0) continue;
                List<Observation> pool = byGroup[0].Rows;
                var counts = pool.GroupBy(x => x.Entity, StringComparer.Ordinal).Select(g => g.Count()).ToList();
                int entities = counts.Count(x => x >= minMeasurements);
                if (entities < 8)
                {
                    notes.Add(Path.GetFileName(file) + ": only " + entities.ToString(CultureInfo.InvariantCulture) + " usable entities in its largest group, skipped.");
                    continue;
                }
                datasets.Add(new RealDataset
                {
                    Name = Path.GetFileNameWithoutExtension(file),
                    FileHash = OutputExporter.HashFile(file),
                    Pool = pool,
                    Entities = entities,
                    MinMeasurements = counts.Count == 0 ? 0 : counts.Min()
                });
            }
            catch (Exception ex)
            {
                notes.Add(Path.GetFileName(file) + ": " + ex.Message);
            }
        }
        return datasets;
    }
}
