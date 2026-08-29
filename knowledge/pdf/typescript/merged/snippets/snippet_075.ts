it('carries a subtype with no typed class (Sound) through unchanged', () => {
      const { dst } = roundTrip();
      const snd = dst.Pages[1].Annotations.find((a) => a.Subtype === 'Sound')!;
      expect(snd.Rect).toEqual([5, 5, 25, 25]);
      expect(snd.Name).toBe('snd-1');
    })