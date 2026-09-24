it('leaves a solid /BE /S /S byte-identical to no /BE', () => {
    expect(squareBody([['BE', be('S')]])).toBe(squareBody([]));
  })