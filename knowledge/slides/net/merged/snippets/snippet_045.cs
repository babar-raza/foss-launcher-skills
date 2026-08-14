[Fact]
    public void TestImageFromFile()
    {
        // Load an image from the test_data directory.
        var imgPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "test_data", "lotus.png");

        using var pres = new Presentation();
        var imageData = File.ReadAllBytes(imgPath);
        var ppImg = pres.Images.AddImage(imageData);
        pres.Slides[0].Shapes!.AddPictureFrame(ShapeType.Rectangle, 50, 50, 200, 200, ppImg);
        pres.Slides[0].Shapes!.Count.Should().BeGreaterThanOrEqualTo(1);
    }