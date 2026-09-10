[Fact]
    public void APictureFrameResolvesTheImageItPointsAt()
    {
        var path = _workspace.PathFor("picture-frame.pptx");

        using (var presentation = new Presentation())
        {
            var image = presentation.Images.AddImage(TestWorkspace.Png());
            presentation.Slides[0].Shapes!.AddPictureFrame(ShapeType.Rectangle, 50, 50, 100, 100, image);
            presentation.Save(path, SaveFormat.Pptx);
        }

        using var package = PptxPackage.Open(path);
        PackageAssert.AllRelationshipReferencesResolve(package);
    }