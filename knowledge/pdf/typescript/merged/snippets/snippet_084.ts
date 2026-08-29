it('reports an out-of-range page rather than throwing', () => {
      const src = Document.Open(buildAnnotRoundtrip());
      const bytes = exportData(src, format, true);
      // A one-page document cannot receive the page-1 annotation.
      const dst = Document.Open(buildAnnotRoundtrip());
      dst.RemovePage(1);
      const report = importData(dst, format, bytes, true);
      expect(report.skippedAnnots).toContainEqual(
        { page: 1, subtype: 'Sound', reason: 'no such page' });
      expect(report.importedAnnots.length).toBe(3);
    })