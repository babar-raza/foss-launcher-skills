it('draws a cloudy polygon as Béziers, not straight segments', () => {
    const { doc, dict } = attach('Polygon', [
      ['Rect', [0, 0, 140, 100]],
      ['Vertices', [20, 20, 120, 20, 70, 80]],
      ['C', [0, 0, 1]],
      ['BE', be('C', 1)],
    ]);
    expect(regenerateAppearance(doc, dict)).toBe(true);
    const body = apBody(doc, dict);
    expect(body).toContain(' c\n');
    expect(body).not.toContain(' l ');
  })