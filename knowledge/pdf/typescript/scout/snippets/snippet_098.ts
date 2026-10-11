it('fills with /C', () => {
    expect(count(render(attach('/Name /Tag /C [1 0 0]')), red, 50, 50, 150, 150)).toBeGreaterThan(200);
  })