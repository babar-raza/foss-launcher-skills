[Fact]
    public void ATableProducesASchemaValidPackage()
    {
        var path = WriteDeckWithATable("table-valid.pptx");

        SchemaValidation.HasNoSchemaErrors(path);
    }