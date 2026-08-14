private static ISlide ClearSlide(Presentation pres)
    {
        pres.Slides[0].Shapes!.Clear();
        return pres.Slides[0];
    }