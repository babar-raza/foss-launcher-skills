[Fact]
    public void SaveToEmlRoundTripsBodiesAndAttachments()
    {
        var message = MapiMessage.Create("RoundTrip", "Plain body");
        message.SenderName = "Alice";
        message.SenderEmailAddress = "alice@example.com";
        message.AddRecipient("bob@example.com", "Bob");
        message.HtmlBody = "<p>Plain body</p>";
        message.AddAttachment("note.txt", "abc"u8.ToArray(), "text/plain");
        message.Attachments.Add(new MapiAttachment
        {
            Filename = "inline.png",
            MimeType = "image/png",
            ContentId = "cid-1",
            Data = "img"u8.ToArray(),
        });

        var reloaded = MapiMessage.LoadFromEml(message.SaveToEml());

        Assert.Equal("RoundTrip", reloaded.Subject);
        Assert.Equal("alice@example.com", reloaded.SenderEmailAddress);
        Assert.Equal("Plain body", reloaded.Body);
        Assert.Equal("<p>Plain body</p>", reloaded.HtmlBody);
        Assert.Equal(2, reloaded.Attachments.Count);
        Assert.Contains(reloaded.Attachments, item => item.Filename == "note.txt" && item.Data.SequenceEqual("abc"u8.ToArray()));
        Assert.Contains(reloaded.Attachments, item => item.ContentId == "cid-1" && item.Data.SequenceEqual("img"u8.ToArray()));
    }