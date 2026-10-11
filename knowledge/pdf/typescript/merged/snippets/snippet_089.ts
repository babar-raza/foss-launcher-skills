it('a present but unusable /AP is respected: nothing is drawn', () => {
    // /N is a state dict and /AS names no state in it.
    const bytes = note('/Name /Note /AP << /N << /On 5 0 R >> >> /AS /Off');
    expect(count(render(bytes), notWhite)).toBe(0);
  })