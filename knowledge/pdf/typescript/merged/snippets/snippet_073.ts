it('leaves /I 0 byte-identical to no /BE', () => {
    expect(squareBody([['BE', be('C', 0)]])).toBe(squareBody([]));
  })