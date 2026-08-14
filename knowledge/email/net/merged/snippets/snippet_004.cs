[Fact]
    public void LoadFromEmlParsesPlainTextHeadersAndBody()
    {
        var eml = """
From: Alice <alice@example.com>
To: Bob <bob@example.com>
Subject: Plain
Message-ID: <plain@example.com>
Date: Tue, 02 Jan 2024 03:04:05 +0000
Content-Type: text/plain; charset=utf-8

Hello from EML.
"""u8.ToArray();

        var message = MapiMessage.LoadFromEml(eml);

        Assert.Equal("Plain", message.Subject);
        Assert.Equal("alice@example.com", message.SenderEmailAddress);
        Assert.Equal("Alice", message.SenderName);
        Assert.Equal("<plain@example.com>", message.InternetMessageId);
        Assert.Equal("Hello from EML.", message.Body?.Trim());
        Assert.Single(message.Recipients);
        Assert.Equal("bob@example.com", message.Recipients[0].EmailAddress);
    }