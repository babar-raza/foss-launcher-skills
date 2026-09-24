it('no /C defaults to a yellow note', () => {
    const img = render(note('/Name /Note'));
    const yellow = ([r, g, b]: number[]) => r > 200 && g > 200 && b < 80;
    expect(count(img, yellow, 50, 50, 150, 150)).toBeGreaterThan(1000);
  })