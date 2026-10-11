[Test]
    public void Save_BasicCmyk_IsByteExact()
    {
        AssertByteExactRoundTrip("basic-cmyk.psd");
    }