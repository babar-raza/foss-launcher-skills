[Fact]
    public void TestPictureFrame()
    {
        // Picture frame with image persists after save/reload.
        using var pres = new Presentation();
        var img = pres.Images.AddImage(TestHelpers.CreateTestPng(0, 0, 255));
        pres.Slides[0].Shapes!.AddPictureFrame(ShapeType.Rectangle, 50, 50, 100, 100, img);
        pres.Slides[0].Shapes!.Count.Should().BeGreaterThanOrEqualTo(1);

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        pres2.Slides[0].Shapes!.Count.Should().BeGreaterThanOrEqualTo(1);
    }