it('reports fdf when no format bit is set', () => {
    const doc = blank();
    expect(roundTrip(doc, { type: 'submit', url: 'u' }))
      .toEqual({ type: 'submit', url: 'u', format: 'fdf' });
  })