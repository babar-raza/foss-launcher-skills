[Fact]
    public void APictureFrameBuiltFromAStreamResolvesTheImageItPointsAt()
    {
        var path = _workspace.PathFor("picture-frame-stream.pptx");

        using (var presentation = new Presentation())
        {
            using var stream = new MemoryStream(TestWorkspace.Png());
            var image = presentation.Images.AddImage(stream);
            presentation.Slides[0].Shapes!.AddPictureFrame(ShapeType.Rectangle, 50, 50, 100, 100, image);
            presentation.Save(path, SaveFormat.Pptx);
        }

        using var package = PptxPackage.Open(path);
        PackageAssert.AllRelationshipReferencesResolve(package);
    }