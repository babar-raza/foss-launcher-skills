[Fact]
    public void TestAddImage()
    {
        // Adding an image increases collection count.
        using var pres = new Presentation();
        pres.Images.AddImage(TestHelpers.CreateTestPng(255, 0, 0));
        pres.Images.Count.Should().BeGreaterThanOrEqualTo(1);
    }