it('encodes ResetForm', () => {
    const bare = encodeAction(blank(), { type: 'reset' });
    expect(nameOf(bare.get('S'))).toBe('ResetForm');
    expect(bare.has('Flags')).toBe(false);
    const scoped = encodeAction(blank(), { type: 'reset', fields: ['a'], exclude: true });
    expect(scoped.get('Flags')).toBe(1);
    expect((scoped.get('Fields') as unknown[]).map(str)).toEqual(['a']);
  })