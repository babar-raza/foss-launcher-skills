[Fact]
    public void TestPictureFill()
    {
        // Picture fill with an image persists.
        using var pres = new Presentation();
        var slide = ClearSlide(pres);
        var shape = slide.Shapes!.AddAutoShape(ShapeType.Rectangle, 50, 50, 200, 200);
        shape.FillFormat.FillType = FillType.Picture;
        var pff = shape.FillFormat.PictureFillFormat;
        pff.PictureFillMode = PictureFillMode.Stretch;
        var img = pres.Images.AddImage(TestHelpers.CreateTestPng(0, 255, 0));
        pff.Picture.Image = img;

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        var ff2 = pres2.Slides[0].Shapes![0].FillFormat;
        ff2.FillType.Should().Be(FillType.Picture);
    }