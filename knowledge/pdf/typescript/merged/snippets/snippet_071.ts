it('carries every non-widget annotation to the right page', () => {
      const { dst, report } = roundTrip();
      expect(report.importedAnnots.length).toBe(4);
      expect(report.skippedAnnots).toEqual([]);
      expect(dst.Pages[0].Annotations.length).toBe(3);
      expect(dst.Pages[1].Annotations.length).toBe(1);
    })