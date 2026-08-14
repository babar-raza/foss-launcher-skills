[Fact]
    public void LoadFromEmlHandlesMultipartRelatedInlineAttachment()
    {
        var imagePayload = Convert.ToBase64String("png"u8.ToArray());
        var eml = $"""
From: Alice <alice@example.com>
To: Bob <bob@example.com>
Subject: Inline
MIME-Version: 1.0
Content-Type: multipart/related; boundary="outer"

--outer
Content-Type: text/html; charset=utf-8
Content-Transfer-Encoding: quoted-printable

<html><body><img src=3D"cid:inline-1"></body></html>
--outer
Content-Type: image/png; name="inline.png"
Content-Transfer-Encoding: base64
Content-Disposition: inline; filename="inline.png"
Content-ID: <inline-1>

{imagePayload}
--outer--
""";

        var message = MapiMessage.LoadFromEml(Encoding.ASCII.GetBytes(eml.Replace("\n", "\r\n", StringComparison.Ordinal)));

        Assert.Contains("cid:inline-1", message.HtmlBody);
        var attachment = Assert.Single(message.Attachments);
        Assert.Equal("inline.png", attachment.Filename);
        Assert.Equal("inline-1", attachment.ContentId);
        Assert.Equal("image/png", attachment.MimeType);
        Assert.Equal("png"u8.ToArray(), attachment.Data);
    }