it('an unknown /Name draws the Note icon, as a viewer does', () => {
    expect(hash(note('/Name /NoSuchIcon'))).toBe(hash(note('/Name /Note')));
    expect(hash(note(''))).toBe(hash(note('/Name /Note')));
  })