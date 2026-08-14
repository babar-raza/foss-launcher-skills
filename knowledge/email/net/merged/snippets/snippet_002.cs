[Fact]
    public void WriterRoundTripsManualDocument()
    {
        var document = new CfbDocument();
        document.Root.AddStream(new CfbStream("A", Encoding.ASCII.GetBytes("hello")));
        var storage = document.Root.AddStorage(new CfbStorage("Storage"));
        storage.AddStream(new CfbStream("BigStream", Encoding.ASCII.GetBytes(new string('x', 6000))));
        storage.AddStream(new CfbStream("Zed", Encoding.ASCII.GetBytes("payload")));

        var payload = CfbWriter.ToBytes(document);

        using var reader = new CfbReader(payload);
        Assert.Equal(3, reader.MajorVersion);
        Assert.Equal(new[] { "A", "Storage" }, reader.IterChildren(CfbConstants.RootStreamId).Select(item => item.Name).ToArray());

        var aStream = reader.ResolvePath(["A"]);
        Assert.NotNull(aStream);
        Assert.Equal("hello", Encoding.ASCII.GetString(reader.GetStreamData(aStream!.StreamId)));

        var bigStream = reader.ResolvePath(["Storage", "BigStream"]);
        Assert.NotNull(bigStream);
        Assert.Equal(6000ul, bigStream!.StreamSize);
    }