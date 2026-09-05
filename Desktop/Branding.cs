using System.Reflection;

namespace MvsAnalyzer;

/// <summary>
/// Logo assets embedded into the executable, so a single published file still
/// carries its own branding and no image has to sit next to the exe. Every
/// loader fails soft: a missing or damaged asset must never stop the
/// application from starting.
/// </summary>
internal static class Branding
{
    private static Image? banner;
    private static bool bannerLoaded;
    private static Icon? icon;
    private static bool iconLoaded;

    /// <summary>Wide wordmark shown inside the application. Null when unavailable.</summary>
    public static Image? Banner
    {
        get
        {
            if (bannerLoaded) return banner;
            bannerLoaded = true;
            byte[]? bytes = Read("inapp_logo.png");
            if (bytes != null)
            {
                try
                {
                    using var stream = new MemoryStream(bytes);
                    using var decoded = Image.FromStream(stream);
                    // Copy the bitmap so it no longer depends on the stream.
                    banner = new Bitmap(decoded);
                }
                catch { banner = null; }
            }
            return banner;
        }
    }

    /// <summary>Multi-size window and taskbar icon. Null when unavailable.</summary>
    public static Icon? AppIcon
    {
        get
        {
            if (iconLoaded) return icon;
            iconLoaded = true;
            byte[]? bytes = Read("app.ico");
            if (bytes != null)
            {
                try
                {
                    using var stream = new MemoryStream(bytes);
                    icon = new Icon(stream);
                }
                catch { icon = null; }
            }
            return icon;
        }
    }

    private static readonly Dictionary<int, Image> colabIcons = new();
    public static Image? ColabIcon(int dpi)
    {
        int size = Math.Clamp((int)Math.Round(32 * dpi / 96.0), 24, 128);
        if (colabIcons.TryGetValue(size, out Image? cached)) return cached;
        int sourceSize = new[] { 32, 48, 64, 96, 192 }.First(x => x >= size);
        byte[]? bytes = Read("colab-" + sourceSize + ".png");
        if (bytes == null) return null;
        using var stream = new MemoryStream(bytes); using Image image = Image.FromStream(stream);
        var scaled = new Bitmap(size, Math.Max(1, (int)Math.Round(size * image.Height / (double)image.Width)));
        using (Graphics g = Graphics.FromImage(scaled))
        {
            g.CompositingQuality = System.Drawing.Drawing2D.CompositingQuality.HighQuality;
            g.InterpolationMode = System.Drawing.Drawing2D.InterpolationMode.HighQualityBicubic;
            g.PixelOffsetMode = System.Drawing.Drawing2D.PixelOffsetMode.HighQuality;
            g.DrawImage(image, new Rectangle(0, 0, scaled.Width, scaled.Height));
        }
        colabIcons[size] = scaled; return scaled;
    }
    public static byte[]? ResourceBytes(string name) => Read(name);

    private static byte[]? Read(string fileName)
    {
        try
        {
            Assembly assembly = typeof(Branding).Assembly;
            string? name = Array.Find(assembly.GetManifestResourceNames(), candidate => candidate.EndsWith(fileName, StringComparison.OrdinalIgnoreCase));
            if (name == null) return null;
            using Stream? stream = assembly.GetManifestResourceStream(name);
            if (stream == null) return null;
            using var buffer = new MemoryStream();
            stream.CopyTo(buffer);
            return buffer.ToArray();
        }
        catch { return null; }
    }
}
