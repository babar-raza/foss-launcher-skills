private static ContentStreamParser CreateParser()
    {
        // ContentStreamParser needs a PdfReader; create a minimal one
        var minimalPdf = Helpers.PdfBuilder.BuildMinimal();
        var reader = PdfReader.FromBytes(minimalPdf);
        return new ContentStreamParser(reader);
    }