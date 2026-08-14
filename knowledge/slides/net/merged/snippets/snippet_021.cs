[Fact]
    public void TestCoreProperties()
    {
        // Core properties persist after save/reload.
        using var pres = new Presentation();
        var props = pres.DocumentProperties;
        props.Title = "My Presentation";
        props.Subject = "Demo Subject";
        props.Author = "John Doe";
        props.Keywords = "demo, test";
        props.Category = "Examples";

        using var pres2 = TestHelpers.SaveAndReopen(pres, _tempDir);
        var p2 = pres2.DocumentProperties;
        p2.Title.Should().Be("My Presentation");
        p2.Subject.Should().Be("Demo Subject");
        p2.Author.Should().Be("John Doe");
        p2.Keywords.Should().Be("demo, test");
        p2.Category.Should().Be("Examples");
    }