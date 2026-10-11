[Fact]
    public void ANotesSlideReferencesANotesMasterThatIsInThePackage()
    {
        var path = WriteDeckWithNotes("notes-master.pptx");

        using var package = PptxPackage.Open(path);

        const string notesSlide = "ppt/notesSlides/notesSlide1.xml";
        Assert.True(package.Contains(notesSlide),
            $"No notes slide was written. Parts: {string.Join(", ", package.PartNames)}");

        var toMaster = package.Relationships(notesSlide)
            .Where(relationship => relationship.Type == Ns.NotesMasterRelationshipType)
            .ToList();

        Assert.True(toMaster.Count == 1,
            $"The notes slide declares {toMaster.Count} notesMaster relationship(s), expected exactly one." +
            $"{Environment.NewLine}{PackageAssert.Describe(package, PptxPackage.RelationshipsPartNameFor(notesSlide))}");

        var target = PptxPackage.ResolveTarget(notesSlide, toMaster[0].Target);
        Assert.True(package.Contains(target),
            $"The notes slide points at '{target}', which is not in the package. " +
            $"Parts: {string.Join(", ", package.PartNames)}");
    }