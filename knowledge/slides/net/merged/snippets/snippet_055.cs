[Fact]
    public void APictureFilledShapeCarriesARealRelationshipAndNoInternalMarker()
    {
        var path = _workspace.PathFor("picture-fill.pptx");

        using (var presentation = new Presentation())
        {
            var image = presentation.Images.AddImage(TestWorkspace.Png());
            var shape = presentation.Slides[0].Shapes!.AddAutoShape(ShapeType.Rectangle, 10, 10, 100, 100);
            shape.FillFormat!.FillType = FillType.Picture;
            shape.FillFormat.PictureFillFormat.Picture.Image = image;
            presentation.Save(path, SaveFormat.Pptx);
        }

        using var package = PptxPackage.Open(path);
        PackageAssert.NoInternalMarkerAttributes(package, "ppt/slides/slide1.xml");
        PackageAssert.AllRelationshipReferencesResolve(package);
    }