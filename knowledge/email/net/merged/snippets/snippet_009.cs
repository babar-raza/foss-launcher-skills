[Fact]
    public void LoadFromEmlHandlesQuotedPrintableHtml()
    {
        var eml = """
From: Alice <alice@example.com>
To: Bob <bob@example.com>
Subject: Html
MIME-Version: 1.0
Content-Type: text/html; charset=utf-8
Content-Transfer-Encoding: quoted-printable

<p>line=20one</p>
"""u8.ToArray();

        var message = MapiMessage.LoadFromEml(eml);

        Assert.Equal("<p>line one</p>", message.HtmlBody);
        Assert.True(string.IsNullOrEmpty(message.Body));
    }