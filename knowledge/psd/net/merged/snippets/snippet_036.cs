[Test]
    public void Load_Resources_ReadsBlocks()
    {
        byte[] resourcesPayload = BuildResourcesPayload(
            (ImageResourceIds.GlobalAngle, "glba", [0x00, 0x00, 0x00, 0x2D]),
            (ImageResourceIds.IccProfile, "icc", [0x49, 0x43, 0x43, 0x50]),
            (ImageResourceIds.IccUntaggedProfile, string.Empty, [0x01]));
        using var stream = new MemoryStream(resourcesPayload);
        using var reader = new BigEndianReader(stream, leaveOpen: true);

        var resources = new List<UnknownResource>();
        while (reader.Position < stream.Length)
        {
            UnknownResource? resource = UnknownResource.Load(reader, stream.Length);
            Assert.That(resource, Is.Not.Null);
            resources.Add(resource!);
        }

        Assert.That(resources, Has.Count.EqualTo(3));
        Assert.That(resources[0].ResourceId, Is.EqualTo(ImageResourceIds.GlobalAngle));
        Assert.That(resources[0].Data, Is.EqualTo(new byte[] { 0x00, 0x00, 0x00, 0x2D }));
        Assert.That(resources[1].ResourceId, Is.EqualTo(ImageResourceIds.IccProfile));
        Assert.That(resources[1].Data, Is.EqualTo(new byte[] { 0x49, 0x43, 0x43, 0x50 }));
        Assert.That(resources[2].ResourceId, Is.EqualTo(ImageResourceIds.IccUntaggedProfile));
        Assert.That(resources[2].Data, Is.EqualTo(new byte[] { 0x01 }));
    }