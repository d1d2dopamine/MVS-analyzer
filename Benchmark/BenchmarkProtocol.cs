using System.Security.Cryptography;
using System.Text;

namespace MvsAnalyzer.Benchmarking;

/// <summary>How much work the benchmark does. Nothing else changes between depths.</summary>
internal enum BenchmarkDepth
{
    Quick = 0,
    Standard = 1,
    Full = 2
}

internal sealed record BenchmarkProfile(
    string Id,
    string Name,
    string NameRu,
    string Estimate,
    string EstimateRu,
    int PrimaryReplications,
    int GridReplications,
    int CalibrationRepetitions,
    int StabilityRepeats,
    int DeterminismReplications);

/// <summary>
/// The decision rules that stand in for a working analyst. The whole benchmark is a comparison
/// between them on data whose truth is known in advance.
/// </summary>
internal static class BenchmarkProcedures
{
    public const int CherryPick = 0;
    public const int Bonferroni = 1;
    public const int FixedMedian = 2;
    public const int FixedCv = 3;
    public const int MvsPilot = 4;
    public const int MvsStrict = 5;
    public const int MvsLenient = 6;
    /// <summary>Added in 1.4.0: calibrates a centre track and a spread track, each at half alpha.</summary>
    public const int MvsTwoTrack = 7;

    public static readonly string[] Ids =
    {
        "cherry_pick", "bonferroni", "fixed_median", "fixed_cv", "mvs_pilot", "mvs_strict", "mvs_lenient", "mvs_two_track"
    };

    public static readonly string[] Labels =
    {
        "Try all ten, report the best",
        "Try all ten, Bonferroni",
        "Median, fixed in advance",
        "Coefficient of variation, fixed in advance",
        "MVS, metric locked on a pilot",
        "MVS, gate respected",
        "MVS, gate ignored",
        "MVS, centre and spread tracks at half alpha each"
    };

    public static readonly string[] LabelsRu =
    {
        "Все десять, выбрать лучшую",
        "Все десять, поправка Бонферрони",
        "Медиана, выбрана заранее",
        "Коэффициент вариации, выбран заранее",
        "MVS, метрика закреплена на пилоте",
        "MVS, порог соблюдён",
        "MVS, порог проигнорирован",
        "MVS, треки центра и разброса, по половине альфы"
    };

    public static readonly string[] Short =
    {
        "cherry-pick", "Bonferroni", "median", "CV", "MVS pilot", "MVS gated", "MVS ungated", "MVS 2-track"
    };

    public static readonly string[] ShortRu =
    {
        "перебор", "Бонферрони", "медиана", "КВ", "MVS пилот", "MVS с порогом", "MVS без порога", "MVS 2 трека"
    };

    public static int Count => Ids.Length;

    public static string Label(int index, bool russian) => russian ? LabelsRu[index] : Labels[index];

    public static string ShortLabel(int index, bool russian) => russian ? ShortRu[index] : Short[index];
}

/// <summary>
/// The frozen part of the benchmark.
///
/// Everything that decides whether the result counts as a success is written here, in the source,
/// and hashed. The hash is pinned by a test and printed into every report and every figure. That is
/// the only honest defence against grading your own homework after the fact: if a threshold is moved
/// to make a bad run look good, the hash in the new report will not match the hash in the old one,
/// and anybody can see it.
/// </summary>
internal static class BenchmarkProtocol
{
    public const string Version = "MVS-BENCH-1.1.0";

    /// <summary>SHA-256 of <see cref="Specification"/>, frozen before the first run of the protocol.</summary>
    public const string FrozenHash = "3bb871b666c189fd8b9188f920108e92b67542b7d63bfe2f1d24393dad5e9723";

    public const string Specification =
        "protocol=MVS-BENCH-1.1.0;" +
        "question=doesMetricSelectionInflateTypeIError;" +
        "designs=gait_stride_like(16x40),voice_jitter_like(20x26);" +
        "shapes=normal,heavy_tail,lognormal;primaryShape=heavy_tail;groups=2;" +
        "test=mannWhitneyTwoSided;alpha=.05;" +
        "injection=location(entityMeanTimesK),dispersion(entityCvTimesK);" +
        "effectGrid=1.00,1.02,1.05,1.10,1.20;primaryLocationK=1.05;primaryDispersionK=1.30;" +
        "contaminationGrid=0,.02,.05,.10;" +
        "procedures=cherry_pick,bonferroni,fixed_median,fixed_cv,mvs_pilot,mvs_strict,mvs_lenient,mvs_two_track;" +
        "shippedDefault=mvs_two_track;" +
        "tracks=location,variability;" +
        "trackCalibration=powerPerTrack,nullAndRobustnessAndRepeatabilityAndCoverageShared;" +
        "twoTrackTest=eachTrackAtAlphaDividedByTrackCount;" +
        "gateAppliedPerTrack;" +
        "oracle=bestFixedMetricPerCondition;oracleSelection=oddReplications;oracleScoring=evenReplications;" +
        "calibration=engine defaults scenario=location effect=1.15 outlierRate=.02 missingRate=0 alpha=.05;" +
        "selection=maxScoreAmongApplicableTieBrokenByMetricOrder;" +
        "strictGate=fpr<=.075 and power>=.70 and score>=60;" +
        "lenientFallback=highestScoringApplicableMetric;" +
        "pilotLockedOnSeparateNullPilotDataset;" +
        "rng=xoshiro256starstar;seedDerivation=splitmix64(seed,stage,condition,replication);" +
        "hypothesisA=cherryPickFpr>=.15 and shippedDefaultFpr<=.075 pass, shippedDefaultFpr>.10 fail;" +
        "hypothesisB=heldOutOraclePowerMinusShippedDefaultPower<=.07 pass, >.15 fail;" +
        "hypothesisC=kendallTauSplitHalf>=.70 and top1Agreement>=.60 pass, tau<.40 fail;" +
        "hypothesisD=mvsStrictFprAtContamination.10<=.075 pass, atContamination.02>.10 fail;" +
        "hypothesisE=identicalSha256AcrossRepeatedRunWithSameSeed;" +
        "monteCarloSe=binomialAndReportedWithEveryRate;" +
        "noResultDependentEdits=protocolHashFrozenInSourceBeforeAnyRun";

    // ---- pre-registered numbers. Changing any line below changes Hash. ----

    public const double Alpha = .05;
    public const double CalibrationEffect = 1.15;
    public const string CalibrationScenario = "location";
    public const double CalibrationOutlierRate = .02;
    public const double CalibrationMissingRate = 0;

    public const double PrimaryLocationEffect = 1.05;
    public const double PrimaryDispersionEffect = 1.30;

    public const double CherryPickFprPass = .15;
    public const double MvsFprPass = .075;
    public const double MvsFprFail = .10;
    public const double PowerLossPass = .07;
    public const double PowerLossFail = .15;
    public const double TauPass = .70;
    public const double TauFail = .40;
    public const double TopOneAgreementPass = .60;
    public const double RobustContamination = .10;
    public const double EarlyContamination = .02;

    public static readonly double[] LocationGrid = { 1.00, 1.02, 1.05, 1.10, 1.20 };
    public static readonly double[] DispersionGrid = { 1.02, 1.05, 1.10, 1.20, 1.30 };
    public static readonly double[] ContaminationGrid = { .02, .05, .10 };

    public static readonly BenchmarkProfile[] Profiles =
    {
        new("quick", "Quick — sanity check", "Быстрый — проверка работоспособности",
            "about 2-5 minutes", "примерно 2-5 минут",
            150, 30, 250, 24, 24),
        new("standard", "Standard — publishable", "Стандартный — можно публиковать",
            "about 15-30 minutes", "примерно 15-30 минут",
            500, 100, 500, 60, 40),
        new("full", "Full — the pre-registered run", "Полный — предзарегистрированный прогон",
            "about 1-2 hours", "примерно 1-2 часа",
            1000, 250, 1000, 120, 60)
    };

    public static string Hash
    {
        get
        {
            byte[] digest = SHA256.HashData(Encoding.UTF8.GetBytes(Specification));
            return Convert.ToHexString(digest).ToLowerInvariant();
        }
    }

    public static bool HashIsFrozen => string.Equals(Hash, FrozenHash, StringComparison.OrdinalIgnoreCase);

    public static BenchmarkProfile Profile(BenchmarkDepth depth)
    {
        int index = Math.Clamp((int)depth, 0, Profiles.Length - 1);
        return Profiles[index];
    }

    public static BenchmarkProfile ProfileById(string id)
    {
        foreach (BenchmarkProfile profile in Profiles)
            if (string.Equals(profile.Id, id, StringComparison.OrdinalIgnoreCase)) return profile;
        return Profiles[0];
    }
}
