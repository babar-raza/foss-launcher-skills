it('an unknown or absent /Name draws the PushPin icon', () => {
    expect(hash(attach('/Name /Nope'))).toBe(hash(attach('/Name /PushPin')));
    expect(hash(attach(''))).toBe(hash(attach('/Name /PushPin')));
  })