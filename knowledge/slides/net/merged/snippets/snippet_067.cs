private static string DescribeWhatWasWritten(string path)
    {
        if (!File.Exists(path))
            return "No file was written.";

        var length = new FileInfo(path).Length;
        try
        {
            using var package = PptxPackage.Open(path);
            var mainType = package.ContentTypeOf("ppt/presentation.xml");
            return $"It wrote a {length}-byte OPC package with {package.PartNames.Count} parts " +
                   $"whose /ppt/presentation.xml is '{mainType ?? "undeclared"}'.";
        }
        catch (Exception)
        {
            return $"It wrote {length} bytes.";
        }
    }