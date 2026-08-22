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
    private static bool TryDouble(string v,bool decimalComma,out double n)
    {
        v=v.Trim().Replace(" ","").Replace("\u00A0","");
        // "1.234,56" is a thousands dot plus a decimal comma; "1234,56" is only a decimal comma.
        v=decimalComma?v.Replace(".","").Replace(',','.'):v.Replace(',','.');
        return double.TryParse(v,NumberStyles.Float,CultureInfo.InvariantCulture,out n)&&double.IsFinite(n);
    }
    // The file is read once as bytes. BOM wins; otherwise strict UTF-8 is tried and
    // Windows-1251 is the fallback, so Cyrillic legacy exports no longer arrive as garbage.
    internal static string ReadText(string path)
    {
        byte[] bytes=File.ReadAllBytes(path);
        if(bytes.Length>=3&&bytes[0]==0xEF&&bytes[1]==0xBB&&bytes[2]==0xBF) return Encoding.UTF8.GetString(bytes,3,bytes.Length-3);
        if(bytes.Length>=2&&bytes[0]==0xFF&&bytes[1]==0xFE) return Encoding.Unicode.GetString(bytes,2,bytes.Length-2);
        if(bytes.Length>=2&&bytes[0]==0xFE&&bytes[1]==0xFF) return Encoding.BigEndianUnicode.GetString(bytes,2,bytes.Length-2);
        try { return new UTF8Encoding(false,true).GetString(bytes); }
        catch(DecoderFallbackException) { return Windows1251(bytes); }
    }
    private const string Windows1251High="ЂЃ‚ѓ„…†‡€‰Љ‹ЊЌЋЏђ‘’“”•–—?™љ›њќћџ ЎўЈ¤Ґ¦§Ё©Є«¬­®Ї°±Ііґµ¶·ё№є»јЅѕїАБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдежзийклмнопрстуфхцчшщъыьэюя";
    private static string Windows1251(byte[] bytes){var s=new StringBuilder(bytes.Length);foreach(byte b in bytes)s.Append(b<0x80?(char)b:Windows1251High[b-0x80]);return s.ToString();}
    private static List<string[]> Parse(string text,char forced=char.MinValue){text=text.TrimStart('\uFEFF');string first=text.Split(new[]{"\r\n","\n"},StringSplitOptions.None)[0];char d=forced!=char.MinValue?forced:new[]{',',';','\t'}.OrderByDescending(x=>first.Count(c=>c==x)).First();var o=new List<string[]>();var row=new List<string>();var cell=new StringBuilder();bool q=false;for(int i=0;i<text.Length;i++){char c=text[i];if(q){if(c=='"'&&i+1<text.Length&&text[i+1]=='"'){cell.Append('"');i++;}else if(c=='"')q=false;else cell.Append(c);}else if(c=='"')q=true;else if(c==d){row.Add(cell.ToString());cell.Clear();}else if(c=='\n'){row.Add(cell.ToString().TrimEnd('\r'));cell.Clear();if(row.Any(x=>x.Length>0))o.Add(row.ToArray());row.Clear();}else cell.Append(c);}row.Add(cell.ToString().TrimEnd('\r'));if(row.Any(x=>x.Length>0))o.Add(row.ToArray());return o;}
}
