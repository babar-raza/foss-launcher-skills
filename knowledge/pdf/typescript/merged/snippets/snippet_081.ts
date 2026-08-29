it('carries no annotations when the export flag is off', () => {
      const src = Document.Open(buildAnnotRoundtrip());
      const bytes = exportData(src, format, false);
      const dst = clearedTarget();
      const report = importData(dst, format, bytes, true);
      expect(report.importedAnnots).toEqual([]);
    })