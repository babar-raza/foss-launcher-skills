it('draws ink inside its /Rect and nothing outside it', () => {
    const img = render(note('/Name /Note'));
    expect(count(img, dark, 50, 50, 150, 150)).toBeGreaterThan(100);
    expect(count(img, notWhite, 0, 0, 200, 45)).toBe(0);
    expect(count(img, notWhite, 0, 155, 200, 200)).toBe(0);
  })