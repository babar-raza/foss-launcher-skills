[Fact]
    public void TestCustomStringProperty()
    {
        // Custom string properties persist.
        using var pres = new Presentation();
        pres.DocumentProperties.SetCustomPropertyValue("MyProp", "hello");

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        var value = pres2.DocumentProperties.GetCustomPropertyValue("MyProp");
        value.Should().Be("hello");
    }