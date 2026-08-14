[Fact]
    public void TestCustomIntProperty()
    {
        // Custom integer properties persist.
        using var pres = new Presentation();
        pres.DocumentProperties.SetCustomPropertyValue("Count", 42);

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        var value = pres2.DocumentProperties.GetCustomPropertyValue("Count");
        value.Should().Be(42);
    }