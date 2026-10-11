it('clamps /I above the spec range rather than scaling past it', () => {
    expect(squareBody([['BE', be('C', 9)]])).toBe(squareBody([['BE', be('C', 2)]]));
  })