private static ISlide BlankSlide(Presentation pres)
    {
        var slide = pres.Slides[0];
        slide.Shapes!.Clear();
        return slide;
    }