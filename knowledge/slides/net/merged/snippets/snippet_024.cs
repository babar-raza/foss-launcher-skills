[Fact]
    public void TestRemoveCustomProperty()
    {
        // Removing a custom property decreases count.
        using var pres = new Presentation();
        var props = pres.DocumentProperties;
        props.SetCustomPropertyValue("A", "val");
        props.SetCustomPropertyValue("B", "val");
        props.CountOfCustomProperties.Should().Be(2);

        props.RemoveCustomProperty("A");
        props.CountOfCustomProperties.Should().Be(1);
        props.ContainsCustomProperty("A").Should().BeFalse();
        props.ContainsCustomProperty("B").Should().BeTrue();
    }