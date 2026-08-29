it('regenerates an appearance for an annotation that arrived without one', () => {
      const { dst } = roundTrip();
      const hi = dst.Pages[0].Annotations.find((a) => a.Subtype === 'Highlight')!;
      expect(apBytes(dst, hi.Dict)).toBeDefined();
    })