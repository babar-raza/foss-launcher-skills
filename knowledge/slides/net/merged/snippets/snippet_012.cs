[Fact]
    public void SavingAfterDisposeRaisesAndWritesNothing()
    {
        var path = _workspace.PathFor("after-dispose.pptx");

        var presentation = new Presentation();
        presentation.Dispose();

        var thrown = Record.Exception(() => presentation.Save(path, SaveFormat.Pptx));

        Assert.True(thrown is ObjectDisposedException,
            $"Save after Dispose {(thrown is null ? "returned successfully" : $"threw {thrown.GetType().Name}")}, " +
            $"expected ObjectDisposedException. " +
            (File.Exists(path)
                ? $"It wrote a {new FileInfo(path).Length}-byte file to the target path."
                : "No file was written."));

        Assert.False(File.Exists(path),
            $"Save after Dispose created '{Path.GetFileName(path)}' " +
            $"({(File.Exists(path) ? new FileInfo(path).Length : 0)} bytes). " +
            "A failed save must not replace what is already at the target path.");
    }