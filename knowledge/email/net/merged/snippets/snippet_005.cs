[Fact]
    public void LoadFromEmlHandlesFoldedHeadersAndBase64Text()
    {
        var body = Convert.ToBase64String(Encoding.UTF8.GetBytes("Base64 body"));
        var eml = $"""
From: Alice <alice@example.com>
To: Bob <bob@example.com>,
 Carol <carol@example.com>
Subject: Folded
Content-Type: text/plain; charset=utf-8
Content-Transfer-Encoding: base64

{body}
""";

        var message = MapiMessage.LoadFromEml(Encoding.ASCII.GetBytes(eml.Replace("\n", "\r\n", StringComparison.Ordinal)));

        Assert.Equal("Folded", message.Subject);
        Assert.Equal("Base64 body", message.Body);
        Assert.Equal(2, message.Recipients.Count);
        Assert.Equal("carol@example.com", message.Recipients[1].EmailAddress);
    }