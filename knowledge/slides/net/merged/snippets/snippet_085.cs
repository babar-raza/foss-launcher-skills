private static void AssertParagraphTexts(PptxPackage package, string[] expected)
    {
        var paragraphs = PackageAssert.Select(package, "ppt/slides/slide1.xml", "//p:txBody/a:p");

        var written = paragraphs
            .Select(paragraph => string.Concat(
                paragraph.Elements(Ns.A + "r").Select(run => run.Element(Ns.A + "t")?.Value ?? string.Empty)))
            .ToList();

        Assert.True(written.SequenceEqual(expected),
            $"The text body carries {written.Count} paragraph(s) [{string.Join(" | ", written)}], " +
            $"expected {expected.Length} [{string.Join(" | ", expected)}]." +
            $"{Environment.NewLine}{PackageAssert.Describe(package, "ppt/slides/slide1.xml")}");
    }