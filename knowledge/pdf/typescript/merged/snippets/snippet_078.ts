it('leaves a generator-less subtype without an appearance, without failing', () => {
      const { dst, report } = roundTrip();
      const snd = dst.Pages[1].Annotations.find((a) => a.Subtype === 'Sound')!;
      expect(apBytes(dst, snd.Dict)).toBeUndefined();
      expect(report.skippedAnnots).toEqual([]);   // not reported as a skip
    })