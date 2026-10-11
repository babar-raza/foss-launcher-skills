it('sets IncludeExclude and writes the field-name list', () => {
    const d = encodeAction(blank(), {
      type: 'submit', url: 'u', fields: ['a', 'b'], exclude: true,
    });
    expect(d.get('Flags')).toBe(1);            // bit 1
    expect((d.get('Fields') as unknown[]).map(str)).toEqual(['a', 'b']);
  })