[Fact]
    public void CanCreateSaveAndReloadMessageUsingStreams()
    {
        var message = MapiMessage.Create("Stream subject", "Stream body");
        message.SenderEmailAddress = "alice@example.com";
        using var attachmentStream = new MemoryStream("stream-data"u8.ToArray());
        message.AddAttachment("stream.txt", attachmentStream, "text/plain");

        using var messageStream = new MemoryStream();
        message.Save(messageStream);
        messageStream.Position = 0;

        var loaded = MapiMessage.FromStream(messageStream);

        Assert.Equal("Stream subject", loaded.Subject);
        Assert.Equal("Stream body", loaded.Body);
        var attachment = Assert.Single(loaded.Attachments);
        Assert.Equal("stream.txt", attachment.Filename);
        Assert.Equal("stream-data"u8.ToArray(), attachment.Data);
    }