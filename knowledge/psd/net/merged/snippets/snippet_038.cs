[Test]
    public void Load_ResourcesFixture_Reads()
    {
        using var image = PsdImage.Load(GetTestDataPath("resources.psd"));

        Assert.That(image.ResourceCount, Is.EqualTo(28));
        Assert.That(image.Resources[0].Kind, Is.EqualTo(PsdResourceKind.Unknown));
        Assert.That(image.HasImageResources, Is.True);
        Assert.That(image.Layers, Has.Length.EqualTo(3));
    }