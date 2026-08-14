[Fact]
    public void CanLoadAndSaveEmlUsingStreams()
    {
        var eml = """
From: Alice <alice@example.com>
To: Bob <bob@example.com>
Subject: Stream EML
Content-Type: text/plain; charset=utf-8

Hello stream.
"""u8.ToArray();

        using var input = new MemoryStream(eml);
        var message = MapiMessage.LoadFromEml(input);

        Assert.Equal("Stream EML", message.Subject);

        using var output = new MemoryStream();
        message.SaveToEml(output);
        output.Position = 0;

        var roundTripped = MapiMessage.LoadFromEml(output);
        Assert.Equal("Stream EML", roundTripped.Subject);
        Assert.Equal("Hello stream.", roundTripped.Body?.Trim());
    }