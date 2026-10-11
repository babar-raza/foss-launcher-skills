[Fact]
    public void CanRoundTripEmbeddedMessageAttachment()
    {
        var parent = MapiMessage.Create("Outer", "Parent body");
        var child = MapiMessage.Create("Inner", "Child body");
        child.SenderEmailAddress = "inner@example.com";
        parent.AddEmbeddedMessageAttachment(child, "inner.msg");

        var tempPath = Path.Combine(Path.GetTempPath(), $"{Guid.NewGuid():N}.msg");
        parent.Save(tempPath);

        try
        {
            var loaded = MapiMessage.FromFile(tempPath);
            var attachment = Assert.Single(loaded.Attachments);
            Assert.True(attachment.IsEmbeddedMessage);
            Assert.Equal("inner.msg", attachment.Filename);
            Assert.NotNull(attachment.EmbeddedMessage);
            Assert.Equal("Inner", attachment.EmbeddedMessage!.Subject);
            Assert.Equal("Child body", attachment.EmbeddedMessage.Body);
            Assert.Equal("inner@example.com", attachment.EmbeddedMessage.SenderEmailAddress);
        }
        finally
        {
            File.Delete(tempPath);
        }
    }