using System.Globalization;
using System.Text;
namespace MvsAnalyzer;
internal static class CsvImporter
{
    // An import profile from a plugin may declare the delimiter, the decimal comma
    // and its own column names. Without a profile the built-in recognition is used.
    public static List<Observation> Read(string path, int minValue, int maxValue, ImportProfile? profile = null)
    {
        string text=ReadText(path); var rows=Parse(text, profile?.Delimiter ?? char.MinValue); if(rows.Count<2) throw new InvalidDataException("The file does not contain data rows.");
        string[] h=rows[0].Select(x=>x.Trim()).ToArray();
        int entity=Find(h,profile,"entity","entity","entity_id","device","device_id","machine","asset","item","sample","object","participant","participant_id","subject","subject_id","id");
        int value=Find(h,profile,"value","value","measurement","reading","result","signal","rt_ms","rt","reaction_time","response_time");
        int group=Find(h,profile,"group","group","condition","class","category","variant","model","arm");
        int sequence=Find(h,profile,"sequence","sequence","index","trial","trial_number","measurement_number","timepoint","step");
        int variable=Find(h,profile,"variable","variable","metric","parameter","measurement_name","signal_name"); int unit=Find(h,profile,"unit","unit","units");
        if(entity<0||value<0||group<0) throw new InvalidDataException("Required roles were not recognized. Use entity/device/item/id, value/measurement/reading and group/condition/class.");
        var output=new List<Observation>(); var counters=new Dictionary<string,int>(StringComparer.OrdinalIgnoreCase); var variables=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        for(int i=1;i<rows.Count;i++) { var r=rows[i]; if(new[]{entity,value,group}.Any(x=>x>=r.Length)) continue; if(!TryDouble(r[value],profile?.DecimalComma ?? false,out double v)||v<minValue||v>maxValue) continue; string e=r[entity].Trim(),g=r[group].Trim(); if(e.Length==0||g.Length==0) continue; string varName=variable>=0&&variable<r.Length&&r[variable].Trim().Length>0?r[variable].Trim():h[value]; string u=unit>=0&&unit<r.Length?r[unit].Trim():""; variables.Add(varName); string key=g+'\u001f'+e; counters.TryGetValue(key,out int n); n++; counters[key]=n; int seq=sequence>=0&&sequence<r.Length&&int.TryParse(r[sequence],out int parsed)?parsed:n; output.Add(new Observation(e,g,v,seq,varName,u)); }
        if(output.Count==0) throw new InvalidDataException($"No valid measurements were found in the {minValue}–{maxValue} range.");
        if(variables.Count>1) throw new InvalidDataException("This version analyzes one variable per run. Filter the file to one variable before import.");
        int groupCount=output.Select(x=>x.Group).Distinct(StringComparer.OrdinalIgnoreCase).Count(); if(groupCount<2||groupCount>10) throw new InvalidDataException("Version 1.0 requires 2–10 groups."); return output;
    }
    private static int Find(string[] h,ImportProfile? profile,string role,params string[] names)
    {
        if(profile!=null&&profile.Columns.TryGetValue(role,out string[]? declared)){int index=Match(h,declared);if(index>=0)return index;}
        return Match(h,names);
    }
    private static int Match(string[] h,string[] names){foreach(string n in names)for(int i=0;i<h.Length;i++)if(string.Equals(h[i].Trim(),n.Trim(),StringComparison.OrdinalIgnoreCase))return i;return-1;}
    private static readonly char[] NumericNoise={(char)32,(char)0x00A0,(char)0x202F,(char)0x2007,(char)0x2009,(char)0x00AD,(char)0x2066,(char)0x2067,(char)0x2068,(char)0x2069};
    internal static bool TryDouble(string v,bool decimalComma,out double n)
    {
        // Spreadsheets export thin, narrow and non breaking spaces as digit group separators,
        // and some locales export a real Unicode minus sign instead of an ASCII hyphen.
        v=new string(v.Trim().Where(c=>Array.IndexOf(NumericNoise,c)<0).ToArray()).Replace((char)0x2212,(char)45);
        // "1.234,56" is a thousands dot plus a decimal comma; "1234,56" is only a decimal comma.
        v=decimalComma?v.Replace(".","").Replace((char)44,(char)46):v.Replace((char)44,(char)46);
        return double.TryParse(v,NumberStyles.Float,CultureInfo.InvariantCulture,out n)&&double.IsFinite(n);
    }
    /// <summary>How the last imported file was decoded. Shown in the UI so a wrong guess is visible.</summary>
    internal static string LastEncodingName { get; private set; } = "utf-8";

    // A BOM wins outright; otherwise strict UTF-8 is tried, and only if that fails do we
    // score the legacy single byte pages against each other instead of assuming one.
    internal static string ReadText(string path)
    {
        string text=Decode(File.ReadAllBytes(path),out string name); LastEncodingName=name; return text;
    }

    internal static string Decode(byte[] bytes,out string encodingName)
    {
        if(bytes.Length>=3&&bytes[0]==0xEF&&bytes[1]==0xBB&&bytes[2]==0xBF){encodingName="utf-8-bom";return Encoding.UTF8.GetString(bytes,3,bytes.Length-3);}
        if(bytes.Length>=2&&bytes[0]==0xFF&&bytes[1]==0xFE){encodingName="utf-16le-bom";return Encoding.Unicode.GetString(bytes,2,bytes.Length-2);}
        if(bytes.Length>=2&&bytes[0]==0xFE&&bytes[1]==0xFF){encodingName="utf-16be-bom";return Encoding.BigEndianUnicode.GetString(bytes,2,bytes.Length-2);}
        // UTF-16 with no BOM: Latin text leaves a zero byte beside every character.
        if(bytes.Length>=4)
        {
            int limit=Math.Min(bytes.Length,4096),evenZero=0,oddZero=0;
            for(int i=0;i+1<limit;i+=2){if(bytes[i]==0)evenZero++;if(bytes[i+1]==0)oddZero++;}
            int pairs=Math.Max(1,limit/2);
            if(oddZero*4>pairs*3&&evenZero*4<pairs){encodingName="utf-16le";return Encoding.Unicode.GetString(bytes);}
            if(evenZero*4>pairs*3&&oddZero*4<pairs){encodingName="utf-16be";return Encoding.BigEndianUnicode.GetString(bytes);}
        }
        try { string utf8=new UTF8Encoding(false,true).GetString(bytes); encodingName="utf-8"; return utf8; }
        catch(DecoderFallbackException) { }
        string best=SingleByte(bytes,Windows1251High),bestName="windows-1251"; double bestScore=Score(best);
        foreach(var candidate in new[]{("cp866",Cp866High),("koi8-r",Koi8RHigh),("windows-1252",Windows1252High)})
        {
            string text=SingleByte(bytes,candidate.Item2); double score=Score(text);
            if(score>bestScore){bestScore=score;best=text;bestName=candidate.Item1;}
        }
        encodingName=bestName; return best;
    }
    // Code page tables are written as escape sequences on purpose. Spelling them as
    // literal Cyrillic made the decoder that repairs mojibake depend on this file itself
    // being read as UTF-8 by the compiler, which is the exact failure it exists to fix.
    private const string Windows1251High="\u0402\u0403\u201A\u0453\u201E\u2026\u2020\u2021\u20AC\u2030\u0409\u2039\u040A\u040C\u040B\u040F\u0452\u2018\u2019\u201C\u201D\u2022\u2013\u2014\uFFFD\u2122\u0459\u203A\u045A\u045C\u045B\u045F\u00A0\u040E\u045E\u0408\u00A4\u0490\u00A6\u00A7\u0401\u00A9\u0404\u00AB\u00AC\u00AD\u00AE\u0407\u00B0\u00B1\u0406\u0456\u0491\u00B5\u00B6\u00B7\u0451\u2116\u0454\u00BB\u0458\u0405\u0455\u0457\u0410\u0411\u0412\u0413\u0414\u0415\u0416\u0417\u0418\u0419\u041A\u041B\u041C\u041D\u041E\u041F\u0420\u0421\u0422\u0423\u0424\u0425\u0426\u0427\u0428\u0429\u042A\u042B\u042C\u042D\u042E\u042F\u0430\u0431\u0432\u0433\u0434\u0435\u0436\u0437\u0438\u0439\u043A\u043B\u043C\u043D\u043E\u043F\u0440\u0441\u0442\u0443\u0444\u0445\u0446\u0447\u0448\u0449\u044A\u044B\u044C\u044D\u044E\u044F";
    private const string Cp866High="\u0410\u0411\u0412\u0413\u0414\u0415\u0416\u0417\u0418\u0419\u041A\u041B\u041C\u041D\u041E\u041F\u0420\u0421\u0422\u0423\u0424\u0425\u0426\u0427\u0428\u0429\u042A\u042B\u042C\u042D\u042E\u042F\u0430\u0431\u0432\u0433\u0434\u0435\u0436\u0437\u0438\u0439\u043A\u043B\u043C\u043D\u043E\u043F\u2591\u2592\u2593\u2502\u2524\u2561\u2562\u2556\u2555\u2563\u2551\u2557\u255D\u255C\u255B\u2510\u2514\u2534\u252C\u251C\u2500\u253C\u255E\u255F\u255A\u2554\u2569\u2566\u2560\u2550\u256C\u2567\u2568\u2564\u2565\u2559\u2558\u2552\u2553\u256B\u256A\u2518\u250C\u2588\u2584\u258C\u2590\u2580\u0440\u0441\u0442\u0443\u0444\u0445\u0446\u0447\u0448\u0449\u044A\u044B\u044C\u044D\u044E\u044F\u0401\u0451\u0404\u0454\u0407\u0457\u040E\u045E\u00B0\u2219\u00B7\u221A\u2116\u00A4\u25A0\u00A0";
    private const string Koi8RHigh="\u2500\u2502\u250C\u2510\u2514\u2518\u251C\u2524\u252C\u2534\u253C\u2580\u2584\u2588\u258C\u2590\u2591\u2592\u2593\u2320\u25A0\u2219\u221A\u2248\u2264\u2265\u00A0\u2321\u00B0\u00B2\u00B7\u00F7\u2550\u2551\u2552\u0451\u2553\u2554\u2555\u2556\u2557\u2558\u2559\u255A\u255B\u255C\u255D\u255E\u255F\u2560\u2561\u0401\u2562\u2563\u2564\u2565\u2566\u2567\u2568\u2569\u256A\u256B\u256C\u00A9\u044E\u0430\u0431\u0446\u0434\u0435\u0444\u0433\u0445\u0438\u0439\u043A\u043B\u043C\u043D\u043E\u043F\u044F\u0440\u0441\u0442\u0443\u0436\u0432\u044C\u044B\u0437\u0448\u044D\u0449\u0447\u044A\u042E\u0410\u0411\u0426\u0414\u0415\u0424\u0413\u0425\u0418\u0419\u041A\u041B\u041C\u041D\u041E\u041F\u042F\u0420\u0421\u0422\u0423\u0416\u0412\u042C\u042B\u0417\u0428\u042D\u0429\u0427\u042A";
    private const string Windows1252High="\u20AC\uFFFD\u201A\u0192\u201E\u2026\u2020\u2021\u02C6\u2030\u0160\u2039\u0152\uFFFD\u017D\uFFFD\uFFFD\u2018\u2019\u201C\u201D\u2022\u2013\u2014\u02DC\u2122\u0161\u203A\u0153\uFFFD\u017E\u0178\u00A0\u00A1\u00A2\u00A3\u00A4\u00A5\u00A6\u00A7\u00A8\u00A9\u00AA\u00AB\u00AC\u00AD\u00AE\u00AF\u00B0\u00B1\u00B2\u00B3\u00B4\u00B5\u00B6\u00B7\u00B8\u00B9\u00BA\u00BB\u00BC\u00BD\u00BE\u00BF\u00C0\u00C1\u00C2\u00C3\u00C4\u00C5\u00C6\u00C7\u00C8\u00C9\u00CA\u00CB\u00CC\u00CD\u00CE\u00CF\u00D0\u00D1\u00D2\u00D3\u00D4\u00D5\u00D6\u00D7\u00D8\u00D9\u00DA\u00DB\u00DC\u00DD\u00DE\u00DF\u00E0\u00E1\u00E2\u00E3\u00E4\u00E5\u00E6\u00E7\u00E8\u00E9\u00EA\u00EB\u00EC\u00ED\u00EE\u00EF\u00F0\u00F1\u00F2\u00F3\u00F4\u00F5\u00F6\u00F7\u00F8\u00F9\u00FA\u00FB\u00FC\u00FD\u00FE\u00FF";
    private static string SingleByte(byte[] bytes,string high){var s=new StringBuilder(bytes.Length);foreach(byte b in bytes)s.Append(b<0x80?(char)b:high[b-0x80]);return s.ToString();}
    // The same byte means a different letter in every legacy page, so the decoding that
    // produces the most plausible text wins instead of Windows-1251 always winning.
    internal static double Score(string text)
    {
        double score=0;
        foreach(char c in text)
        {
            if(c>=(char)0x0430&&c<=(char)0x044F) score+=3;
            else if(c>=(char)0x0410&&c<=(char)0x042F) score+=2;
            else if(c==(char)0x0451||c==(char)0x0401) score+=2;
            else if(c<(char)128&&char.IsLetterOrDigit(c)) score+=1;
            else if(c==(char)32||c==(char)44||c==(char)59||c==(char)46||c==(char)9||c==(char)13||c==(char)10) score+=.5;
            else if(c==(char)0xFFFD||char.IsControl(c)) score-=8;
            else score-=1;
        }
        return score;
    }
    private static List<string[]> Parse(string text,char forced=char.MinValue){text=text.TrimStart('\uFEFF');string first=text.Split(new[]{"\r\n","\n"},StringSplitOptions.None)[0];char d=forced!=char.MinValue?forced:new[]{',',';','\t'}.OrderByDescending(x=>first.Count(c=>c==x)).First();var o=new List<string[]>();var row=new List<string>();var cell=new StringBuilder();bool q=false;for(int i=0;i<text.Length;i++){char c=text[i];if(q){if(c=='"'&&i+1<text.Length&&text[i+1]=='"'){cell.Append('"');i++;}else if(c=='"')q=false;else cell.Append(c);}else if(c=='"')q=true;else if(c==d){row.Add(cell.ToString());cell.Clear();}else if(c=='\n'){row.Add(cell.ToString().TrimEnd('\r'));cell.Clear();if(row.Any(x=>x.Length>0))o.Add(row.ToArray());row.Clear();}else cell.Append(c);}row.Add(cell.ToString().TrimEnd('\r'));if(row.Any(x=>x.Length>0))o.Add(row.ToArray());return o;}
}
