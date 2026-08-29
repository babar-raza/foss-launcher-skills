it('never carries the widget annotation', () => {
      const { dst } = roundTrip();
      for (const p of dst.Pages)
        for (const a of p.Annotations) expect(a.Subtype).not.toBe('Widget');
    })