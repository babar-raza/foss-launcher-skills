it('encodes a URI action', () => {
    const d = encodeAction(blank(), { type: 'uri', uri: 'https://example.com' });
    expect(nameOf(d.get('S'))).toBe('URI');
    expect(str(d.get('URI'))).toBe('https://example.com');
  })