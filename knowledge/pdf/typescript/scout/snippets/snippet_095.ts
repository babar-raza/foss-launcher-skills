it('draws ink inside its /Rect', () => {
    expect(count(render(attach('/Name /PushPin')), dark, 50, 50, 150, 150)).toBeGreaterThan(50);
  })