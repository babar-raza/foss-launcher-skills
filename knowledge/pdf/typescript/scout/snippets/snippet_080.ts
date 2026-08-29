it('is idempotent: importing twice does not duplicate', () => {
      const src = Document.Open(buildAnnotRoundtrip());
      const bytes = exportData(src, format, true);
      const dst = Document.Open(buildAnnotRoundtrip());
      importData(dst, format, bytes, true);
      const afterFirst = dst.Pages.map((p) => p.Annotations.length);
      importData(dst, format, bytes, true);
      expect(dst.Pages.map((p) => p.Annotations.length)).toEqual(afterFirst);
    })