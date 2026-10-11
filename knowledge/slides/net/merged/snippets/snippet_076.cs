[Fact]
    public void ATableReferencesItsStyleThroughTheSchemaElementName()
    {
        var path = WriteDeckWithATable("table-style-id.pptx");

        using var package = PptxPackage.Open(path);

        var wrongName = PackageAssert.Select(package, "ppt/slides/slide1.xml", "//a:tblPr/a:tblStyleId");
        Assert.True(wrongName.Count == 0,
            $"The table style is written as <a:tblStyleId>, which is not an element of CT_TableProperties. " +
            $"ECMA-376 names it <a:tableStyleId>.{Environment.NewLine}" +
            $"written: {string.Join(", ", wrongName)}");

        PackageAssert.SingleElement(package, "ppt/slides/slide1.xml", "//a:tblPr/a:tableStyleId");
    }