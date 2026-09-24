it('fills with /C', () => {
    const img = render(note('/Name /Note /C [1 0 0]'));
    expect(count(img, red, 50, 50, 150, 150)).toBeGreaterThan(1000);
  })