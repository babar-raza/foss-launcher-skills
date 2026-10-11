it('defaults an absent /I beside /S /C to a cloud, not to nothing', () => {
    // /S /C is the request for a cloud; reading a missing /I as 0 would make
    // the dictionary mean nothing.
    expect(squareBody([['BE', be('C')]])).not.toBe(squareBody([]));
  })