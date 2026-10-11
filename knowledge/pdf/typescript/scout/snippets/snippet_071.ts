it('draws a cloudy square as Béziers, not a rectangle', () => {
    const { doc, dict } = attach('Square', [
      ['Rect', [0, 0, 120, 80]],
      ['C', [1, 0, 0]],
      ['BE', be('C', 2)],
    ]);
    expect(regenerateAppearance(doc, dict)).toBe(true);
    const body = apBody(doc, dict);
    expect(body).toContain(' c\n');
    expect(body).not.toContain(' re');
  })