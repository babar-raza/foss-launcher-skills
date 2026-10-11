[Test]
    public void Load_NullStream_Throws()
    {
        Assert.That(() => PsdImage.Load((Stream)null!), Throws.InstanceOf<ArgumentNullException>());
    }