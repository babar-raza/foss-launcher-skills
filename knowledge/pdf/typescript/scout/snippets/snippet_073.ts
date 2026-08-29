it('preserves properties on the highlight', () => {
      const { dst } = roundTrip();
      const hi = dst.Pages[0].Annotations.find((a) => a.Subtype === 'Highlight')!;
      expect(hi.Rect).toEqual([0, 0, 100, 20]);
      expect(hi.Color).toEqual([1, 1, 0]);
      expect(hi.Opacity).toBeCloseTo(0.4, 6);
      expect(hi.Contents).toBe('a reply');
    })