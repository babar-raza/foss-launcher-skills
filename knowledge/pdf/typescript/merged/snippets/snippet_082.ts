it('ignores annotations in the file when the import flag is off', () => {
      const src = Document.Open(buildAnnotRoundtrip());
      const bytes = exportData(src, format, true);
      const dst = clearedTarget();
      const report = importData(dst, format, bytes, false);
      expect(report.importedAnnots).toEqual([]);
      expect(dst.Pages[0].Annotations.length).toBe(0);
    })