[Fact]
    public void TestMultipleImages()
    {
        // Multiple images can be added and iterated.
        using var pres = new Presentation();
        var colors = new (byte r, byte g, byte b)[] { (255, 0, 0), (0, 255, 0), (0, 0, 255) };
        foreach (var (r, g, b) in colors)
        {
            pres.Images.AddImage(TestHelpers.CreateTestPng(r, g, b));
        }

        pres.Images.Count.Should().BeGreaterThanOrEqualTo(3);
        var imgs = pres.Images.AsIEnumerable.ToList();
        imgs.Count.Should().BeGreaterThanOrEqualTo(3);
    }