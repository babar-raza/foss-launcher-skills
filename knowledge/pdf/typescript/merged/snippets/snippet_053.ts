it('encodes a GoTo action with a destination array', () => {
    const doc = blank();
    const d = encodeAction(doc, { type: 'goto', page: 1 });
    expect(nameOf(d.get('S'))).toBe('GoTo');
    expect(Array.isArray(d.get('D'))).toBe(true);
  })