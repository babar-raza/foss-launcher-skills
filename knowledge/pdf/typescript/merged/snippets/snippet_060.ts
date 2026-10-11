it('round-trips every action type', () => {
    const doc = blank();
    expect(roundTrip(doc, { type: 'uri', uri: 'https://x' }))
      .toEqual({ type: 'uri', uri: 'https://x' });
    expect(roundTrip(doc, { type: 'javascript', script: 's' }))
      .toEqual({ type: 'javascript', script: 's' });
    expect(roundTrip(doc, { type: 'reset' })).toEqual({ type: 'reset' });
    expect(roundTrip(doc, { type: 'reset', fields: ['a'], exclude: true }))
      .toEqual({ type: 'reset', fields: ['a'], exclude: true });
    expect(roundTrip(doc, { type: 'submit', url: 'u', format: 'xfdf' }))
      .toEqual({ type: 'submit', url: 'u', format: 'xfdf' });
    expect(roundTrip(doc, { type: 'submit', url: 'u', fields: ['a'], exclude: true }))
      .toEqual({ type: 'submit', url: 'u', fields: ['a'], exclude: true, format: 'fdf' });
  })