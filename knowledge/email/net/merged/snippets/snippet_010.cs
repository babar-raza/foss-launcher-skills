[Fact]
    public void CanCreateSaveAndReloadMessageWithSenderRecipientAndAttachment()
    {
        var message = MapiMessage.Create("Hello", "Body");
        message.SenderName = "Alice";
        message.SenderEmailAddress = "alice@example.com";
        message.InternetMessageId = "<hello@example.com>";
        message.MessageDeliveryTime = new DateTime(2024, 1, 2, 3, 4, 5, DateTimeKind.Utc);
        message.AddRecipient("bob@example.com", "Bob");
        message.AddAttachment("note.txt", "abc"u8.ToArray(), "text/plain");

        var bytes = message.Save();
        var tempPath = Path.Combine(Path.GetTempPath(), $"{Guid.NewGuid():N}.msg");
        File.WriteAllBytes(tempPath, bytes);

        try
        {
            var loaded = MapiMessage.FromFile(tempPath);
            Assert.Equal("Hello", loaded.Subject);
            Assert.Equal("Body", loaded.Body);
            Assert.Equal("Alice", loaded.SenderName);
            Assert.Equal("alice@example.com", loaded.SenderEmailAddress);
            Assert.Equal("<hello@example.com>", loaded.InternetMessageId);
            Assert.Equal(new DateTime(2024, 1, 2, 3, 4, 5, DateTimeKind.Utc), loaded.MessageDeliveryTime);
            Assert.Single(loaded.Recipients);
            Assert.Equal("bob@example.com", loaded.Recipients[0].EmailAddress);
            Assert.Single(loaded.Attachments);
            Assert.Equal("note.txt", loaded.Attachments[0].Filename);
            Assert.Equal("text/plain", loaded.Attachments[0].MimeType);
            Assert.Equal("abc"u8.ToArray(), loaded.Attachments[0].Data);
        }
        finally
        {
            File.Delete(tempPath);
        }
    }