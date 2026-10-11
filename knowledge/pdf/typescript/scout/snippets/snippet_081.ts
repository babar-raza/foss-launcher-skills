it('an empty /C draws the outline only (transparent, 12.5.2)', () => {
    const img = render(note('/Name /Note /C []'));
    expect(count(img, dark, 50, 50, 150, 150)).toBeGreaterThan(100);
    // Only the outline and rules are ink: the body stays white.
    expect(count(img, notWhite, 50, 50, 150, 150)).toBeLessThan(3000);
  })