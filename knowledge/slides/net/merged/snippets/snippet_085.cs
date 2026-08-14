[Fact]
    public void TestInsertEmptySlide()
    {
        // insert_empty_slide places a slide at the given index.
        using var pres = new Presentation();
        var layout = pres.LayoutSlides[0];
        pres.Slides.AddEmptySlide(layout);
        pres.Slides.InsertEmptySlide(1, layout);
        pres.Slides.Count.Should().Be(3);
    }