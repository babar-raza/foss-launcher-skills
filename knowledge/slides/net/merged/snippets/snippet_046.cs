[Fact]
    public void AGraphicFrameLocksItsContentsThroughTheSchemaElementName()
    {
        var path = _workspace.PathFor("graphic-frame-locks.pptx");

        using (var presentation = new Presentation())
        {
            presentation.Slides[0].Shapes!.AddTable(50, 50, [100, 100], [30, 30]);
            presentation.Save(path, SaveFormat.Pptx);
        }

        using var package = PptxPackage.Open(path);

        PackageAssert.SingleElement(package, "ppt/slides/slide1.xml", "//p:cNvGraphicFramePr/a:graphicFrameLocks");
        Assert.Empty(PackageAssert.Select(package, "ppt/slides/slide1.xml", "//a:graphicFrameLocking"));
    }