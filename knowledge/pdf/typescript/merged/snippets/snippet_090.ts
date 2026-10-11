it('a Hidden note stays blank', () => {
    expect(count(render(note('/Name /Note /F 2')), notWhite)).toBe(0);
  })