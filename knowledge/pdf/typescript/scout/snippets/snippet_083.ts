it('still carries field values alongside the annotations', () => {
      const src = Document.Open(buildAnnotRoundtrip());
      const bytes = exportData(src, format, true);
      const dst = Document.Open(buildAnnotRoundtrip());
      const report = importData(dst, format, bytes, true);
      expect(report.imported).toContain('field1');
    })