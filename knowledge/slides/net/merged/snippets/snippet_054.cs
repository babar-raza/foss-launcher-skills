[Fact]
    public void AnEmbeddedImageDeclaresItsContentType()
    {
        var path = _workspace.PathFor("picture-content-type.pptx");

        using (var presentation = new Presentation())
        {
            var image = presentation.Images.AddImage(TestWorkspace.Png());
            presentation.Slides[0].Shapes!.AddPictureFrame(ShapeType.Rectangle, 50, 50, 100, 100, image);
            presentation.Save(path, SaveFormat.Pptx);
        }

        using var package = PptxPackage.Open(path);

        var media = package.PartNames.Where(n => n.StartsWith("ppt/media/", StringComparison.Ordinal)).ToList();
        Assert.True(media.Count > 0, $"No media part was written. Parts: {string.Join(", ", package.PartNames)}");

        PackageAssert.EveryPartHasItsRequiredContentType(package);
    }